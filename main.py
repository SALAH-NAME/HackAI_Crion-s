import os
from contextlib import asynccontextmanager
from typing import List, Dict, Any, Optional
from pathlib import Path

# FastAPI imports
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Core LangChain imports
from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.chains import RetrievalQA
from langchain.agents import initialize_agent, AgentType, Tool
from langchain.memory import ConversationBufferMemory
from langchain.prompts import PromptTemplate

# Google Gemini LLM
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

# Vector store
from langchain_community.vectorstores import FAISS

# Document loaders
from langchain_community.document_loaders import UnstructuredMarkdownLoader

class MarkdownRAGSystem:
    """RAG system that processes Markdown files using Google Gemini and FAISS"""
    
    def __init__(self, google_api_key: str, markdown_files: List[str] = None):
        """
        Initialize the RAG system
        
        Args:
            google_api_key: Google API key for Gemini
            markdown_files: List of markdown file paths to process
        """
        os.environ["GOOGLE_API_KEY"] = google_api_key
        
        self.markdown_files = markdown_files or ["sample.md"]
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            temperature=0.1,
            convert_system_message_to_human=True
        )
        
        self.embeddings = GoogleGenerativeAIEmbeddings(
            model="models/embedding-001"
        )
        
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
            separators=["\n\n", "\n", " ", ""]
        )
        
        self.vectorstore = None
        self.retrieval_qa = None
        
    def load_markdown_documents(self) -> List[Document]:
        """Load and process markdown documents from specified files"""
        print(f"Loading markdown documents from files: {self.markdown_files}")
        
        documents = []
        
        for file_path in self.markdown_files:
            file_path = Path(file_path)
            
            if not file_path.exists():
                # Create sample file if it doesn't exist
                if file_path.name == "sample.md":
                    sample_content = """# Sample Knowledge Base

## Introduction
This is a sample knowledge base for the RAG system.

## Features
- Markdown document processing
- Vector similarity search
- Question answering capabilities
- Translation services

## Usage
Ask questions about the content in the knowledge base, and the system will provide relevant answers based on the documents."""
                    
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(sample_content)
                    print(f"Created sample file: {file_path}")
                else:
                    print(f"Warning: File {file_path} not found, skipping...")
                    continue
            
            try:
                loader = UnstructuredMarkdownLoader(str(file_path))
                doc = loader.load()[0]  # UnstructuredMarkdownLoader returns a list
                doc.metadata["source"] = str(file_path)
                documents.append(doc)
                print(f"Loaded: {file_path}")
            except Exception as e:
                print(f"Error loading {file_path}: {e}")
                continue
        
        print(f"Successfully loaded {len(documents)} markdown documents")
        return documents
    
    def create_vectorstore(self, documents: List[Document]) -> None:
        """Create FAISS vector store from documents"""
        print("Splitting documents into chunks...")
        texts = self.text_splitter.split_documents(documents)
        print(f"Created {len(texts)} text chunks")
        
        print("Creating FAISS vector store...")
        self.vectorstore = FAISS.from_documents(
            documents=texts,
            embedding=self.embeddings
        )
        print("Vector store created successfully")
    
    def setup_retrieval_qa(self) -> None:
        """Setup the retrieval QA chain"""
        if not self.vectorstore:
            raise ValueError("Vector store not initialized. Call create_vectorstore first.")
        
        # Custom prompt template for RAG
        prompt_template = """Use the following pieces of context to answer the question at the end. 
        If you don't know the answer based on the context, just say that you don't know, don't try to make up an answer.

        Context: {context}

        Question: {question}
        
        Answer: """
        
        PROMPT = PromptTemplate(
            template=prompt_template,
            input_variables=["context", "question"]
        )
        
        self.retrieval_qa = RetrievalQA.from_chain_type(
            llm=self.llm,
            chain_type="stuff",
            retriever=self.vectorstore.as_retriever(
                search_type="similarity",
                search_kwargs={"k": 4}
            ),
            chain_type_kwargs={"prompt": PROMPT},
            return_source_documents=True
        )
    
    def query(self, question: str) -> Dict[str, Any]:
        """Query the RAG system"""
        if not self.retrieval_qa:
            raise ValueError("Retrieval QA not initialized. Call setup_retrieval_qa first.")
        
        result = self.retrieval_qa({"query": question})
        
        return {
            "answer": result["result"],
            "source_documents": [
                {
                    "content": doc.page_content[:200] + "...",
                    "source": doc.metadata.get("source", "unknown")
                }
                for doc in result["source_documents"]
            ]
        }

class TranslationAgent:
    """Agent for translating text using Google Gemini"""
    
    def __init__(self, llm):
        self.llm = llm
    
    def detect_language(self, text: str) -> str:
        """Detect the language of the input text"""
        prompt = f"""Detect the language of the following text. Respond with ONLY the language name in English (e.g., "English", "Spanish", "French", "German", etc.).
        
        Text: {text}
        
        Language:"""
        
        response = self.llm.invoke(prompt)
        return response.content.strip()
    
    def translate_text(self, text: str, target_language: str = "Spanish") -> str:
        """Translate text to target language"""
        prompt = f"""Translate the following text to {target_language}. 
        Provide only the translation without any additional commentary.
        
        Text to translate: {text}
        
        Translation:"""
        
        response = self.llm.invoke(prompt)
        return response.content
    
    def detect_and_translate(self, text: str, target_language: str = "English") -> Dict[str, str]:
        """Detect source language and translate"""
        detection_prompt = f"""Analyze this text and identify its language, then translate it to {target_language}.
        
        Format your response as:
        Source Language: [detected language]
        Translation: [translated text]
        
        Text: {text}"""
        
        response = self.llm.invoke(detection_prompt)
        content = response.content
        
        # Parse response
        lines = content.strip().split('\n')
        source_lang = "Unknown"
        translation = content
        
        for line in lines:
            if line.startswith("Source Language:"):
                source_lang = line.replace("Source Language:", "").strip()
            elif line.startswith("Translation:"):
                translation = line.replace("Translation:", "").strip()
        
        return {
            "source_language": source_lang,
            "translation": translation
        }

class RAGTranslationSystem:
    """Combined RAG and Translation system with LangChain agents"""
    
    def __init__(self, google_api_key: str, markdown_files: List[str] = None):
        self.rag_system = MarkdownRAGSystem(google_api_key, markdown_files)
        self.translator = TranslationAgent(self.rag_system.llm)
        
        # Memory for conversation
        self.memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True
        )
        
        self.agent = None
    
    def initialize(self):
        """Initialize the complete system"""
        print("Initializing RAG Translation System...")
        
        # Load documents and create vector store
        documents = self.rag_system.load_markdown_documents()
        self.rag_system.create_vectorstore(documents)
        self.rag_system.setup_retrieval_qa()
        
        # Setup agent tools
        self._setup_agent()
        
        print("System initialized successfully!")
    
    def _setup_agent(self):
        """Setup LangChain agent with tools"""
        def rag_query_tool(query: str) -> str:
            """Query the RAG knowledge base"""
            try:
                result = self.rag_system.query(query)
                answer = result["answer"]
                sources = ", ".join([doc["source"] for doc in result["source_documents"]])
                return f"Answer: {answer}\n\nSources: {sources}"
            except Exception as e:
                return f"Error querying knowledge base: {str(e)}"
        
        def translation_tool(text_and_language: str) -> str:
            """Translate text. Input format: 'text|||target_language'"""
            try:
                parts = text_and_language.split("|||")
                text = parts[0].strip()
                target_lang = parts[1].strip() if len(parts) > 1 else "Spanish"
                
                result = self.translator.detect_and_translate(text, target_lang)
                return f"Source Language: {result['source_language']}\nTranslation: {result['translation']}"
            except Exception as e:
                return f"Error in translation: {str(e)}"
        
        tools = [
            Tool(
                name="RAG_Query",
                func=rag_query_tool,
                description="Use this to answer questions based on the markdown knowledge base. Input should be a clear question."
            ),
            Tool(
                name="Translate",
                func=translation_tool,
                description="Use this to translate text. Input format: 'text|||target_language' (e.g., 'Hello world|||Spanish')"
            )
        ]
        
        self.agent = initialize_agent(
            tools=tools,
            llm=self.rag_system.llm,
            agent=AgentType.CONVERSATIONAL_REACT_DESCRIPTION,
            memory=self.memory,
            verbose=True,
            handle_parsing_errors=True
        )
    
    def chat(self, message: str) -> str:
        """Chat with the agent"""
        if not self.agent:
            return "System not initialized. Call initialize() first."
        
        try:
            response = self.agent.run(message)
            return response
        except Exception as e:
            return f"Error: {str(e)}"
    
    def chat_with_language_matching(self, message: str) -> Dict[str, str]:
        """Chat with automatic language detection and matching"""
        if not self.agent:
            return {"error": "System not initialized. Call initialize() first."}
        
        try:
            # Detect the language of the user's question
            user_language = self.translator.detect_language(message)
            
            # If it's not English, translate the question to English for processing
            if user_language.lower() != "english":
                translation_result = self.translator.detect_and_translate(message, "English")
                english_question = translation_result["translation"]
                print(f"Detected language: {user_language}")
                print(f"Translated question: {english_question}")
            else:
                english_question = message
                print(f"Detected language: English")
            
            # Process the question (in English) with the agent
            english_response = self.agent.run(english_question)
            
            # If user's language was not English, translate the response back
            if user_language.lower() != "english":
                final_response = self.translator.translate_text(english_response, user_language)
                print(f"Translated response back to {user_language}")
            else:
                final_response = english_response
            
            return {
                "user_language": user_language,
                "original_question": message,
                "english_question": english_question if user_language.lower() != "english" else None,
                "english_response": english_response if user_language.lower() != "english" else None,
                "final_response": final_response,
                "status": "success"
            }
            
        except Exception as e:
            return {
                "error": f"Error: {str(e)}",
                "status": "error"
            }
    
    def add_document(self, content: str, filename: str) -> str:
        """Add a new document to the knowledge base"""
        try:
            # Save to file
            file_path = Path(filename)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            
            # Add to file list and reload
            if str(file_path) not in self.rag_system.markdown_files:
                self.rag_system.markdown_files.append(str(file_path))
            
            # Reload and update vector store
            documents = self.rag_system.load_markdown_documents()
            self.rag_system.create_vectorstore(documents)
            self.rag_system.setup_retrieval_qa()
            
            return f"Document '{filename}' added successfully to the knowledge base."
        except Exception as e:
            return f"Error adding document: {str(e)}"

# Global system instance
system = None

# @app.on_event("startup")
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the RAG Translation System on startup"""
    global system
    
    # Get API key from environment
    google_api_key = os.getenv("GOOGLE_API_KEY")
    if not google_api_key:
        raise ValueError("GOOGLE_API_KEY environment variable is required")
    
    # Initialize with default files or from environment
    # markdown_files = os.getenv("MARKDOWN_FILES", []).split(",")
    markdown_files = ["abroad.md", "nation.md"]
    markdown_files = [f.strip() for f in markdown_files if f.strip()]
    
    system = RAGTranslationSystem(google_api_key, markdown_files)
    system.initialize()
    print("RAG Translation System initialized successfully!")
    yield

# FastAPI Application
app = FastAPI(lifespan=lifespan, title="RAG Translation System", description="LangChain RAG with Translation Agent")

origins = [
    "http://localhost:8000",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,

    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "OK"}

@app.get("/ask")
async def ask_question(q: str = Query(..., description="Question to ask the RAG system")):
    """Ask a question to the RAG Translation System with automatic language matching"""
    global system
    
    if not system:
        raise HTTPException(status_code=503, detail="System not initialized")
    
    try:
        # Use the new language-matching chat method
        result = system.chat_with_language_matching(q)
        
        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("error"))
        
        return {
            "question": result["original_question"],
            "detected_language": result["user_language"],
            "answer": result["final_response"],
            "status": "success",
            # Include translation details for debugging (optional)
            "debug_info": {
                "english_question": result.get("english_question"),
                "english_response": result.get("english_response")
            } if result.get("english_question") else None
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing question: {str(e)}")

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    """Serve the index.html file"""
    try:
        return FileResponse("index.html")
    except FileNotFoundError:
        # Create a default index.html if it doesn't exist
        default_html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RAG Translation System</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
        .container { background: #f5f5f5; padding: 20px; border-radius: 8px; }
        input[type="text"] { width: 70%; padding: 10px; margin: 10px 0; }
        button { padding: 10px 20px; background: #007cba; color: white; border: none; border-radius: 4px; cursor: pointer; }
        button:hover { background: #005a87; }
        .response { margin-top: 20px; padding: 15px; background: white; border-radius: 4px; border-left: 4px solid #007cba; }
    </style>
</head>
<body>
    <div class="container">
        <h1>RAG Translation System</h1>
        <p>Ask questions about the knowledge base or request translations!</p>
        
        <div>
            <input type="text" id="questionInput" placeholder="Enter your question..." />
            <button onclick="askQuestion()">Ask</button>
        </div>
        
        <div id="response" class="response" style="display: none;">
            <h3>Response:</h3>
            <p id="responseText"></p>
        </div>
    </div>

    <script>
        async function askQuestion() {
            const question = document.getElementById('questionInput').value;
            if (!question.trim()) return;
            
            const responseDiv = document.getElementById('response');
            const responseText = document.getElementById('responseText');
            
            responseDiv.style.display = 'block';
            responseText.innerHTML = 'Processing...';
            
            try {
                const response = await fetch(`/ask?q=${encodeURIComponent(question)}`);
                const data = await response.json();
                
                if (data.status === 'success') {
                    responseText.innerHTML = `
                        <strong>Q (${data.detected_language}):</strong> ${data.question}<br><br>
                        <strong>A:</strong> ${data.answer}
                        ${data.debug_info ? `<br><br><small><strong>Debug:</strong> Question processed in English: "${data.debug_info.english_question}"</small>` : ''}
                    `;
                } else {
                    responseText.innerHTML = `Error: ${data.detail || 'Unknown error'}`;
                }
            } catch (error) {
                responseText.innerHTML = `Error: ${error.message}`;
            }
        }
        
        // Allow Enter key to submit
        document.getElementById('questionInput').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                askQuestion();
            }
        });
    </script>
</body>
</html>"""
        
        with open("index.html", "w", encoding="utf-8") as f:
            f.write(default_html)
        
        return HTMLResponse(content=default_html)

# Development server runner
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
