from flask import Blueprint, render_template, jsonify, request, abort
from flask_login import login_required, current_user
from .src.helper import download_hugging_face_embeddings
from langchain_pinecone import PineconeVectorStore
from langchain_openai import ChatOpenAI
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv
from .src.prompt import *
import os


rag_bp = Blueprint(
    "rag",
    __name__,
    template_folder="templates",
    static_folder="static",
    url_prefix="/rag"
)


# Load env from project root and from this module's folder
load_dotenv()  # root .env
_rag_env = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_rag_env):
    load_dotenv(_rag_env, override=True)


PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_API_URL = os.getenv("OPENROUTER_API_URL")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL")


os.environ["OPENROUTER_API_URL"] = OPENROUTER_API_URL or os.environ.get("OPENROUTER_API_URL", "")
os.environ["OPENROUTER_MODEL"] = OPENROUTER_MODEL or os.environ.get("OPENROUTER_MODEL", "")
os.environ["PINECONE_API_KEY"] = PINECONE_API_KEY or os.environ.get("PINECONE_API_KEY", "")
os.environ["OPENROUTER_API_KEY"] = OPENROUTER_API_KEY or os.environ.get("OPENROUTER_API_KEY", "")


def _has(x):
    return bool(x and x.strip())

CONFIG_OK = all([
    _has(PINECONE_API_KEY),
    _has(OPENROUTER_API_KEY),
    _has(OPENROUTER_API_URL),
    _has(OPENROUTER_MODEL)
])

embeddings = None
docsearch = None
retriever = None
chatModel = None
question_answer_chain = None
rag_chain = None
CONFIG_ERROR = None

if CONFIG_OK:
    try:
        embeddings = download_hugging_face_embeddings()
        index_name = "medical-chatbot"
        docsearch = PineconeVectorStore.from_existing_index(
            index_name=index_name,
            embedding=embeddings
        )
        retriever = docsearch.as_retriever(search_type="similarity", search_kwargs={"k": 3})
        chatModel = ChatOpenAI(
            model=OPENROUTER_MODEL,
            api_key=OPENROUTER_API_KEY,
            base_url=OPENROUTER_API_URL,
        )
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                ("human", "{input}"),
            ]
        )
        question_answer_chain = create_stuff_documents_chain(chatModel, prompt)
        rag_chain = create_retrieval_chain(retriever, question_answer_chain)
    except Exception as e:
        CONFIG_OK = False
        CONFIG_ERROR = str(e)




@rag_bp.route("/")
@login_required
def rag_home():
    return render_template('rag_chat.html', config_ok=CONFIG_OK, config_error=CONFIG_ERROR)



@rag_bp.route("/get", methods=["GET", "POST"])
@login_required
def rag_chat():
    if not CONFIG_OK or rag_chain is None:
        return "Chatbot not available. Check model and vector index configuration.", 503
    try:
        msg = request.form["msg"]
        response = rag_chain.invoke({"input": msg})
        return str(response["answer"])
    except Exception as e:
        return f"Upstream error: {e}", 502

@rag_bp.before_request
def require_patient_role():
    if not getattr(current_user, "is_authenticated", False):
        return
    if current_user.role != "patient":
        abort(403)
