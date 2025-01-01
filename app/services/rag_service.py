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
        print(f"Knowledge base IDs: {knowledge_base_ids}")
        print(f"Enabled document IDs: {enabled_document_ids}")
        print(f"User ID: {user_id}")
        
        # Sanitize collection name
        collection_name = user_id.replace('.', '_').replace('@', '_')
        while '__' in collection_name:
            collection_name = collection_name.replace('__', '_')
        collection_name = collection_name.rstrip('_')
        print(f"Using collection name: {collection_name}")
        
        # Get embeddings for the query
        print("\n=== Getting Query Embeddings ===")
        query_embedding = await self.get_embedding(query, chat_id, user_id)
        print("Successfully got query embeddings")
        
        # Format the lists for Milvus expression
        kb_ids_str = "['" + "','".join(knowledge_base_ids) + "']"
        doc_ids_str = "['" + "','".join(enabled_document_ids) + "']"
        print(f"\n=== Milvus Search ===")
        
        # Extract contexts from search results
        print("\n=== Processing Search Results ===")
        contexts = []
        
        # Search for each document individually to ensure we get one result from each
        for doc_id in enabled_document_ids:
            doc_filter = f"knowledge_base_id in {kb_ids_str} and document_id == '{doc_id}'"
            print(f"\nSearching for document {doc_id}")
            print(f"Filter: {doc_filter}")
            
            try:
                doc_results = self.milvus_client.search(
                    collection_name=collection_name,
                    data=[query_embedding],
                    limit=1,  # Get top match for this document
                    output_fields=["text", "knowledge_base_id", "document_id", "document_name"],
                    filter=doc_filter,
                    search_params={"nprobe": 10},
                    consistency_level="Strong"
                )
                
                if doc_results and len(doc_results) > 0 and len(doc_results[0]) > 0:
                    hit = doc_results[0][0]  # Get the first (and only) result
                    entity = hit['entity']
                    
                    # Check for required fields, use document_id as fallback for document_name
                    if 'text' in entity and 'document_id' in entity:
                        # Use document_name if available, otherwise use a generic name
                        doc_name = entity.get('document_name', 'Additional Document')
                        contexts.append({
                            'text': entity['text'],
                            'document_name': doc_name
                        })
                        print("\nFound context:")
                        print(f"Text (first 100 chars): {entity['text'][:100]}...")
                        print(f"Document: {doc_name}")
                        print(f"Document ID: {entity['document_id']}")
                        if 'knowledge_base_id' in entity:
                            print(f"Knowledge base ID: {entity['knowledge_base_id']}")
                    else:
                        print(f"Warning: Missing required fields in search result for document {doc_id}")
                        print(f"Available fields: {list(entity.keys())}")
                else:
                    print(f"No matching content found for document {doc_id}")
                    
            except Exception as e:
                print(f"Error searching for document {doc_id}: {str(e)}")
                print(f"Error type: {type(e)}")
                continue
        
        if not contexts:
            print("WARNING: No contexts found in any documents")
        else:
            print(f"\nTotal contexts found: {len(contexts)} from {len(enabled_document_ids)} enabled documents")
        
        return contexts

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
        
        # Format chat history into a conversation string
        conversation_context = ""
        if chat_history:
            for msg in chat_history:
                role = "Assistant" if msg["role"] == "assistant" else "Human"
                conversation_context += f"{role}: {msg['content']}\n"
        
        # Construct the system message with both document context and chat history
        system_message = """You are a helpful AI assistant. Answer the question based on the following context and chat history.

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

Here is the context to use:\n\n"""
        
        if contexts:
            system_message += "Context from documents:\n"
            for context in contexts:
                system_message += f"\nFrom document '{context['document_name']}':\n{context['text']}\n"
            system_message += "\n"
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