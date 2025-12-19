#!/usr/bin/env python3
"""
LlamaStack RAG Test

Simple script to test RAG functionality with LlamaStack.
Creates a vector store, inserts documents, and performs RAG queries.

Usage:
    python rag-test.py [options]

Options:
    --llamastack-url URL            LlamaStack server URL
    --inference-model MODEL         Inference model for RAG generation
    --embedding-model MODEL         Embedding model for vector store
    --embedding-dimension DIM       Dimension of embedding vectors
    --vector-store-provider PROVIDER Vector store provider (e.g., milvus, faiss)

Environment Variables:
    LLAMASTACK_URL: LlamaStack server URL
    INFERENCE_MODEL: Inference model name
    EMBEDDING_MODEL: Embedding model name
    EMBEDDING_DIMENSION: Dimension of embedding vectors
    VECTOR_STORE_PROVIDER: Vector store provider name
"""

import os
import sys
import argparse
import urllib3
import httpx
import uuid
from typing import Optional
from openai import OpenAI
from llama_stack_client import LlamaStackClient

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class RAGTest:
    def __init__(
        self, 
        llamastack_url: str,
        inference_model: str,
        embedding_model: str,
        embedding_dimension: int,
        vector_store_provider: str
    ):
        self.llamastack_url = llamastack_url.rstrip('/')
        self.inference_model = inference_model
        self.embedding_model = embedding_model
        self.embedding_dimension = embedding_dimension
        self.vector_store_provider = vector_store_provider
        
        self.openai_client = None
        self.client = None
        
        self.sample_docs = [
            "Our secret name is Paul French.",
            "Our favorite HEX color is #cf3a24.",
            "Our favorite planet name is Gaia."
        ]

    def initialize_clients(self):
        """Initialize OpenAI and LlamaStack clients"""
        self.openai_client = OpenAI(
            base_url=f"{self.llamastack_url}/v1/openai/v1",
            api_key="dummy",
            http_client=httpx.Client(verify=False)
        )
        
        self.client = LlamaStackClient(
            base_url=self.llamastack_url,
            http_client=httpx.Client(verify=False)
        )

    def create_vector_store(self) -> Optional[str]:
        """Create a vector store""" 
        
        print("\n[1/3] Creating vector store...")
        
        try:
            response = self.client.vector_stores.create(
                name=f"rag-test-{uuid.uuid4().hex[:8]}",
                extra_body={
                    "embedding_model": self.embedding_model,
                    "embedding_dimension": self.embedding_dimension,
                    "provider_id": self.vector_store_provider
                } 
            )
            print(f"      Created: {response.id}")
            return response.id
        except Exception as e:
            print(f"      Error: {e}")
            return None

    def insert_documents(self, vector_store_id: str) -> bool:
        """Insert documents into vector store"""
        print(f"\n[2/3] Inserting {len(self.sample_docs)} documents...")
        
        try:
            chunks = []
            for i, doc in enumerate(self.sample_docs):
                chunks.append({
                    "content": doc,
                    "metadata": {"document_id": f"doc-{i}", "index": i}
                })
            
            self.client.vector_io.insert(
                vector_db_id=vector_store_id,
                chunks=chunks
            )
            print(f"      Inserted {len(chunks)} chunks")
            return True
        except Exception as e:
            print(f"      Error: {e}")
            return False

    def query_rag(self, vector_store_id: str, query: str) -> Optional[str]:
        """Query using RAG"""
        try:
            result = self.client.vector_io.query(
                vector_db_id=vector_store_id,
                query=query,
                params={"k": 2}
            )
            
            context_docs = []
            for chunk in result.chunks:
                context_docs.append(str(chunk.content))
            
            if not context_docs:
                print("      No relevant chunks found")
                return None
            
            context = "\n\n".join(context_docs)
            
            messages = [
                {
                    "role": "system",
                    "content": f"Answer the question based on the following context:\n\n{context}"
                },
                {
                    "role": "user",
                    "content": query
                }
            ]
            
            response = self.openai_client.chat.completions.create(
                model=self.inference_model,
                messages=messages,
                max_tokens=200
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            print(f"      Error: {e}")
            return None

    def run_test(self):
        """Run RAG test"""
        print("=" * 60)
        print("RAG Test Configuration")
        print("=" * 60)
        print(f"LlamaStack URL:       {self.llamastack_url}")
        print(f"Inference Model:      {self.inference_model}")
        print(f"Embedding Model:      {self.embedding_model}")
        print(f"Embedding Dimension:  {self.embedding_dimension}")
        print(f"Vector Store:         {self.vector_store_provider}")
        print("=" * 60)

        self.initialize_clients()

        vector_store_id = self.create_vector_store()
        if not vector_store_id:
            return False
        
        if not self.insert_documents(vector_store_id):
            return False
        
        print("\n[3/3] Testing RAG queries...")
        queries = [
            "What is our secret name? In one short sentence.",
            "What is our favorite HEX color? In one short sentence.",
            "What is our favorite planet name? In one short sentence.",
        ]
        
        for i, query in enumerate(queries, 1):
            print(f"\n   Query {i}: {query}")
            answer = self.query_rag(vector_store_id, query)
            if answer:
                print(f"   Answer: {answer}")
                ## asseet that the answer is in the sample_docs
                print(f"Answer: {answer}")
                print(f"Sample docs: {self.sample_docs}")
                assert answer in self.sample_docs, f"Answer {answer} is not in the sample docs"
        
        print(f"Answer: {answer}")
        print("\n" + "=" * 60)
        print("RAG test completed successfully")
        print("=" * 60)
        return True

def main():
    parser = argparse.ArgumentParser(
        description="LlamaStack RAG Test",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "--llamastack-url", 
        default=os.getenv("LLAMASTACK_URL", "http://localhost:8321"),
        help="LlamaStack server URL (env: LLAMASTACK_URL)"
    )
    
    parser.add_argument(
        "--inference-model",
        default=os.getenv("INFERENCE_MODEL", "vllm-inference/llama-3-2-3b"),
        help="Inference model for RAG (env: INFERENCE_MODEL)"
    )
    
    parser.add_argument(
        "--embedding-model",
        default=os.getenv("EMBEDDING_MODEL", "sentence-transformers/nomic-ai/nomic-embed-text-v1.5"),
        help="Embedding model for vector store (env: EMBEDDING_MODEL)"
    )
    
    parser.add_argument(
        "--embedding-dimension",
        type=int,
        default=int(os.getenv("EMBEDDING_DIMENSION", "768")),
        help="Dimension of embedding vectors (env: EMBEDDING_DIMENSION)"
    )
    
    parser.add_argument(
        "--vector-store-provider",
        default=os.getenv("VECTOR_STORE_PROVIDER", "milvus"),
        help="Vector store provider (env: VECTOR_STORE_PROVIDER)"
    )

    args = parser.parse_args()

    test = RAGTest(
        llamastack_url=args.llamastack_url,
        inference_model=args.inference_model,
        embedding_model=args.embedding_model,
        embedding_dimension=args.embedding_dimension,
        vector_store_provider=args.vector_store_provider
    )
    
    success = test.run_test()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
