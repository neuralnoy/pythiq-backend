from typing import List, Dict
from pymilvus import MilvusClient
from ..core.config import settings
from openai import OpenAI
from langchain_openai import OpenAIEmbeddings
import os
from ..db.repositories.token_usage import token_usage_repository
import tiktoken

class RAGService:
    def __init__(self):
        self.api_key = settings.OPENAI_API_KEY
        print("Initializing RAGService")
        self.embeddings = OpenAIEmbeddings(api_key=self.api_key)
        
        self.milvus_client = MilvusClient(
            uri=settings.ZILLIZ_CLOUD_URI,
            token=settings.ZILLIZ_CLOUD_API_KEY
        )
        print("RAGService initialized successfully")
        
    def count_tokens(self, text: str) -> int:
        """Count tokens in a text string using tiktoken"""
        encoding = tiktoken.encoding_for_model("gpt-4")
        return len(encoding.encode(text))
        
    async def get_embedding(self, text: str, chat_id: str, user_id: str) -> List[float]:
        """Get embeddings using langchain OpenAIEmbeddings"""
        print(f"Getting embeddings for text: {text[:100]}...")
        try:
            # Count tokens for the text being embedded
            token_count = self.count_tokens(text)
            
            # Get the embedding
            embedding = self.embeddings.embed_query(text)
            print(f"Successfully got embeddings of length: {len(embedding)}")
            
            # Record token usage for embedding
            await token_usage_repository.create_usage_record(
                user_id=user_id,
                chat_id=chat_id,
                completion_tokens=0,
                prompt_tokens=0,
                embedding_tokens=token_count,
                operation_type="embedding"
            )
            
            return embedding
        except Exception as e:
            print(f"Error getting embeddings: {str(e)}")
            raise

    async def get_relevant_chunks(
        self,
        query: str,
        knowledge_base_ids: List[str],
        enabled_document_ids: List[str],
        user_id: str,
        chat_id: str
    ) -> List[Dict]:
        print("\n=== Getting Relevant Chunks ===")
        print(f"Query: {query}")
        
        # Sanitize collection name (same as before)
        collection_name = user_id.replace('.', '_').replace('@', '_')
        while '__' in collection_name:
            collection_name = collection_name.replace('__', '_')
        collection_name = collection_name.rstrip('_')
        
        # Get embeddings for the query
        query_embedding = await self.get_embedding(query, chat_id, user_id)
        
        # Format the lists for Milvus expression
        kb_ids_str = "['" + "','".join(knowledge_base_ids) + "']"
        
        # Initialize containers for results
        all_chunks = []
        chunks_by_doc = {}
        
        # Step 1: Get top 3 chunks from each document
        for doc_id in enabled_document_ids:
            doc_filter = f"knowledge_base_id in {kb_ids_str} and document_id == '{doc_id}'"
            
            try:
                doc_results = self.milvus_client.search(
                    collection_name=collection_name,
                    data=[query_embedding],
                    limit=3,  # Get top 3 matches per document
                    output_fields=["text", "knowledge_base_id", "document_id", "document_name"],
                    filter=doc_filter,
                    search_params={"nprobe": 10},
                    consistency_level="Strong"
                )
                
                if doc_results and len(doc_results) > 0:
                    # Print just one debug line per document search
                    print(f"Found {len(doc_results[0])} results for document {doc_id}")
                    
                    for hit in doc_results[0]:  # Process all hits
                        if isinstance(hit, dict):
                            entity = hit.get('entity', {})
                            score = hit.get('distance', 0)  # Try 'distance' instead of 'score'
                            
                            if 'text' in entity and 'document_id' in entity:
                                doc_name = entity.get('document_name', 'Additional Document')
                                chunk = {
                                    'text': entity['text'],
                                    'document_name': doc_name,
                                    'document_id': entity['document_id'],
                                    'score': score
                                }
                                all_chunks.append(chunk)
                                
                                # Group chunks by document
                                if doc_id not in chunks_by_doc:
                                    chunks_by_doc[doc_id] = []
                                chunks_by_doc[doc_id].append(chunk)
                        else:
                            print(f"Unexpected hit format: {type(hit)}")
                            
            except Exception as e:
                print(f"Error searching for document {doc_id}: {str(e)}")
                print(f"Full error details: {type(e).__name__}: {str(e)}")
                print(f"Doc results structure: {doc_results if 'doc_results' in locals() else 'No results'}")
                continue
        
        # Step 2: Global reranking - sort all chunks by score
        all_chunks.sort(key=lambda x: x['score'], reverse=True)
        
        # Step 3: Ensure representation and build final context
        final_chunks = []
        
        # FIRST PASS: MANDATORY - Include the best chunk from EACH document
        missing_docs = []
        for doc_id in enabled_document_ids:
            if doc_id in chunks_by_doc and chunks_by_doc[doc_id]:
                # Get the best chunk for this document
                best_chunk = max(chunks_by_doc[doc_id], key=lambda x: x['score'])
                final_chunks.append(best_chunk)
            else:
                missing_docs.append(doc_id)
                print(f"Warning: No chunks found for document {doc_id}")
        
        if missing_docs:
            error_msg = f"Critical: Could not find chunks for {len(missing_docs)} documents: {missing_docs}"
            print(error_msg)
            raise ValueError(error_msg)
        
        # SECOND PASS: Add additional high-scoring chunks that meet the similarity threshold
        SIMILARITY_THRESHOLD = 0.75
        max_chunks = len(enabled_document_ids) * 3  # Allow up to 3 chunks per document
        
        # Add more chunks from the globally ranked list if they meet the threshold
        for chunk in all_chunks:
            if len(final_chunks) >= max_chunks:
                break
            if chunk not in final_chunks and chunk['score'] >= SIMILARITY_THRESHOLD:  # Add similarity threshold check
                final_chunks.append(chunk)
        
        # Sort final chunks by score for optimal presentation
        final_chunks.sort(key=lambda x: x['score'], reverse=True)
        
        # Print score distribution for debugging
        print("\nScore distribution in final chunks:")
        print(f"Min score: {min(chunk['score'] for chunk in final_chunks):.4f}")
        print(f"Max score: {max(chunk['score'] for chunk in final_chunks):.4f}")
        print(f"Threshold: {SIMILARITY_THRESHOLD}")
        
        # Step 4: Format the final context and verify representation
        contexts = []
        represented_docs = set()
        
        for chunk in final_chunks:
            contexts.append({
                'text': chunk['text'],
                'document_name': chunk['document_name'],
                'score': chunk['score']
            })
            represented_docs.add(chunk['document_id'])
            
            print(f"\nIncluded chunk from {chunk['document_name']} (score: {chunk['score']:.4f})")
        
        # Final verification - double check all documents are represented
        missing_in_final = set(enabled_document_ids) - represented_docs
        if missing_in_final:
            error_msg = f"Critical: Final context missing chunks from documents: {missing_in_final}"
            print(error_msg)
            raise ValueError(error_msg)
        
        print(f"\nTotal contexts selected: {len(contexts)}")
        print(f"Documents represented: {len(represented_docs)} out of {len(enabled_document_ids)}")
        
        return contexts

    def manage_context_window(
        self,
        system_message: str,
        chat_history: List[Dict],
        query: str,
        max_tokens: int = 120000  # 128000 - 8000 buffer
    ) -> List[Dict]:
        """Manage the context window size by removing old messages if needed."""
        # First, calculate tokens in the fixed parts
        total_tokens = self.count_tokens(system_message)
        total_tokens += self.count_tokens(query)
        
        if not chat_history:
            return []
            
        # Calculate tokens for each message and create a list of (message, tokens) tuples
        message_tokens = []
        for msg in chat_history:
            tokens = self.count_tokens(msg["content"])
            message_tokens.append((msg, tokens))
            total_tokens += tokens
        
        # If we're under the limit, return the full history
        if total_tokens <= max_tokens:
            return chat_history
            
        # We need to remove old messages. Keep removing from the start until we're under the limit
        # Always keep at least the last message pair (human + assistant) if possible
        while total_tokens > max_tokens and len(message_tokens) > 2:
            removed_msg, removed_tokens = message_tokens.pop(0)
            total_tokens -= removed_tokens
        
        # Return the remaining messages
        return [msg for msg, _ in message_tokens]

    async def generate_response(
        self,
        query: str,
        contexts: List[Dict],
        chat_history: List[Dict] = None,
        chat_id: str = None,
        user_id: str = None
    ) -> str:
        print("\n=== Generating Response ===")
        print(f"Query: {query}")
        
        # Construct the system message first
        system_message = """You are a helpful AI assistant. Your name is PythiQ. Answer the question based on the following context and chat history.

When structuring your response:
1. Start with a brief overall summary if the question warrants it
2. Then, present information from each document separately using this format:

📄 [Document Name]
Then continue with the content WITHOUT using any additional document icons:
- Information from this document
- Continue with bullet points for key information
- Make sure all points under this section come from this document only

3. When referring to documents in your response text:
   - Simply use the document name without the 📄 icon
   - If a document has a proper name, use that name
   - For documents without proper names, generate and refer to them as natural phrases based on the document's content
   - NEVER use or mention any document IDs, UUIDs, or technical identifiers
   - If there are multiple unnamed documents, differentiate them naturally (e.g., 'First Market Report', 'Second Market Report')
4. Focus on the content and insights rather than document identifiers
5. Always maintain clear visual separation between information from different documents using the format above
6. Keep the document naming consistent throughout your response
7. Format your response using markdown:
   - Use **bold** for emphasis
   - Use proper heading levels (##, ###) for section titles
   - Use proper markdown lists (-, *) for bullet points
   - Use proper markdown tables when presenting tabular data
   - Use proper markdown links when referencing URLs
8. When writing mathematical equations:
   - Use markdown code blocks with 'math' language identifier for equations
   - Format each equation as a separate code block like this:
     ```math
     equation here
     ```
   - For inline equations, use single backticks with 'math' like this: `math: equation here`
   - Write equations in a simple ASCII format that's easy to read
   - Use ^ for exponents, * for multiplication, / for division
   - Use descriptive variable names when possible
   - Add line breaks and proper spacing in complex equations for readability
   - Example display equation:
     ```math
     y = (-b + sqrt(b^2 - 4*a*c)) / (2*a)
     ```
   - Example inline equation: `math: f(x) = x^2`
9. Images or figures are represented by the following format:
   - ![Image or Figure here: \n **Description of the image or figure, generated by AI:**: \n\n {description} \n\n **End of the description.** ] \n\n
   - The description is generated by AI and is a short description of the image or figure
   - Try to identify which image or figure is being referred to in the text
   - If there are multiple images or figures, try to identify which one is being referred to in the text
   - If the user asks for a specific image or figure, try to identify which one is being referred to in the text
10. Don't reply out of your general knowledge. All the information you need is in the context.
Here is the context to use:\n\n"""
        
        if contexts:
            system_message += "Context from documents:\n"
            for context in contexts:
                system_message += f"\nFrom document '{context['document_name']}':\n{context['text']}\n"
            system_message += "\n"
            
        # Manage context window size
        managed_history = self.manage_context_window(system_message, chat_history, query) if chat_history else None
        
        # Format chat history into a conversation string
        conversation_context = ""
        if managed_history:
            for msg in managed_history:
                role = "Assistant" if msg["role"] == "assistant" else "Human"
                conversation_context += f"{role}: {msg['content']}\n"
                
        if conversation_context:
            system_message += "Previous conversation:\n" + conversation_context
        
        client = OpenAI(api_key=self.api_key)
        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": query}
        ]
        
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0,
                max_tokens=4000
            )
            
            # Record token usage for chat completion
            if chat_id and user_id:
                await token_usage_repository.create_usage_record(
                    user_id=user_id,
                    chat_id=chat_id,
                    completion_tokens=response.usage.completion_tokens,
                    prompt_tokens=response.usage.prompt_tokens,
                    operation_type="chat"
                )
            
            return response.choices[0].message.content
        except Exception as e:
            print(f"Error generating response: {str(e)}")
            raise 