from typing import List, Dict
from pymilvus import MilvusClient
from ..core.config import settings
from openai import OpenAI
from langchain_openai import OpenAIEmbeddings
import os

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
        
    async def get_embedding(self, text: str) -> List[float]:
        """Get embeddings using langchain OpenAIEmbeddings"""
        print(f"Getting embeddings for text: {text[:100]}...")
        try:
            embedding = self.embeddings.embed_query(text)
            print(f"Successfully got embeddings of length: {len(embedding)}")
            return embedding
        except Exception as e:
            print(f"Error getting embeddings: {str(e)}")
            raise
        
    async def get_relevant_chunks(
        self,
        query: str,
        knowledge_base_ids: List[str],
        enabled_document_ids: List[str],
        user_id: str
    ) -> List[str]:
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
        query_embedding = await self.get_embedding(query)
        print("Successfully got query embeddings")
        
        # Format the lists for Milvus expression
        kb_ids_str = "['" + "','".join(knowledge_base_ids) + "']"
        doc_ids_str = "['" + "','".join(enabled_document_ids) + "']"
        filter_expr = f"knowledge_base_id in {kb_ids_str} and document_id in {doc_ids_str}"
        print(f"\n=== Milvus Search ===")
        print(f"Filter expression: {filter_expr}")
        
        # Search in Milvus with properly formatted expression
        print("Starting Milvus search...")
        try:
            search_results = self.milvus_client.search(
                collection_name=collection_name,
                data=[query_embedding],
                limit=len(enabled_document_ids),
                output_fields=["text", "knowledge_base_id", "document_id"],
                filter=filter_expr
            )
            print(f"Milvus search completed. Got {len(search_results) if search_results else 0} results")
        except Exception as e:
            print(f"Error searching in Milvus: {str(e)}")
            raise
        
        # Extract contexts from search results
        print("\n=== Processing Search Results ===")
        contexts = []
        if search_results and len(search_results) > 0:
            for hit in search_results[0]:
                contexts.append(hit['entity']['text'])
                print("\nFound context:")
                print(f"Text (first 100 chars): {hit['entity']['text'][:100]}...")
                print(f"Document ID: {hit['entity']['document_id']}")
                print(f"Knowledge base ID: {hit['entity']['knowledge_base_id']}")
        else:
            print("WARNING: No contexts found in search results")
        
        print(f"\nTotal contexts found: {len(contexts)}")
        return contexts

    async def generate_response(
        self,
        query: str,
        contexts: List[str],
        chat_history: List[Dict] = None
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
        system_message = "You are a helpful AI assistant. Answer the question based on the following context and chat history.\n\n"
        if contexts:
            system_message += "Context from documents:\n" + "\n".join(contexts) + "\n\n"
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
            return response.choices[0].message.content
        except Exception as e:
            print(f"Error generating response: {str(e)}")
            raise 