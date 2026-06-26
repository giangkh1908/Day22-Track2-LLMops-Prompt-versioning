"""
Bước 2 — Prompt Hub & A/B Routing
===================================
NHIỆM VỤ:
  1. Viết 2 system prompt khác nhau (V1: ngắn gọn, V2: có cấu trúc)
  2. Push cả 2 lên LangSmith Prompt Hub qua client.push_prompt()
  3. Pull lại từ Hub qua client.pull_prompt()
  4. Implement A/B routing tất định: hash(request_id) % 2 → V1 hoặc V2
  5. Chạy 50 câu hỏi qua router → ≥ 50 LangSmith traces nữa

DELIVERABLE: 2 prompt version hiển thị trong Prompt Hub trên https://smith.langchain.com
"""
import sys
import hashlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import config  # ⚠️ phải import trước LangChain

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langsmith import Client, traceable

from utils.llm_factory import get_llm, get_embeddings
from utils.data_loader import load_knowledge_base, split_text, build_vectorstore
from qa_pairs import SAMPLE_QUESTIONS


# ── 1. Tên Prompt trên Hub ─────────────────────────────────────────────────
# TODO hoàn thành: Đổi thành tên prompt ổn định, dễ nhận diện trong Prompt Hub.
PROMPT_V1_NAME = "day22-lab-rag-prompt-v1"
PROMPT_V2_NAME = "day22-lab-rag-prompt-v2"


# ── 2. Định nghĩa 2 Prompt Templates ──────────────────────────────────────
# TODO hoàn thành: SYSTEM_V1 theo phong cách ngắn gọn, trả lời 2-4 câu.
SYSTEM_V1 = (
    "Bạn là trợ lý AI hữu ích. Chỉ dùng context sau để trả lời câu hỏi. "
    "Trả lời ngắn gọn, trực tiếp trong 2-4 câu. "
    "Nếu context không có đủ thông tin, hãy nói rõ rằng bạn không tìm thấy thông tin phù hợp.\n\n"
    "Context:\n{context}"
)

# TODO hoàn thành: PROMPT_V1 nhận context từ system message và question từ human message.
PROMPT_V1 = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_V1),
    ("human",  "{question}"),
])

# TODO hoàn thành: SYSTEM_V2 theo phong cách có cấu trúc, expert tone, 3-5 câu.
SYSTEM_V2 = (
    "Bạn là chuyên gia phân tích AI. Đọc kỹ context, xác định các facts liên quan, "
    "rồi trả lời có cấu trúc trong 3-5 câu. "
    "Bắt đầu bằng ý chính, sau đó giải thích ngắn gọn dựa trên context. "
    "Không suy đoán ngoài dữ liệu được cung cấp; nếu thiếu thông tin, hãy nêu rõ giới hạn đó.\n\n"
    "Context:\n{context}"
)

# TODO hoàn thành: PROMPT_V2 nhận context từ system message và question từ human message.
PROMPT_V2 = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_V2),
    ("human",  "{question}"),
])


# ── 3. Push Prompts lên Prompt Hub ─────────────────────────────────────────
def push_prompts_to_hub(client: Client):
    """
    Upload cả 2 prompt templates lên LangSmith Prompt Hub.
    Gợi ý: client.push_prompt(name, object=template, description="...")
    """
    # TODO hoàn thành: Push PROMPT_V1, bọc try/except để script vẫn báo lỗi rõ ràng.
    try:
        url = client.push_prompt(
            PROMPT_V1_NAME,
            object=PROMPT_V1,
            description="V1 - ngắn gọn, trực tiếp",
        )
        print(f"✅ Đã push V1 → {url}")
    except Exception as e:
        print(f"⚠️  V1 lỗi: {e}")

    # TODO hoàn thành: Push PROMPT_V2, bọc try/except để script vẫn báo lỗi rõ ràng.
    try:
        url = client.push_prompt(
            PROMPT_V2_NAME,
            object=PROMPT_V2,
            description="V2 - có cấu trúc, tone chuyên gia",
        )
        print(f"✅ Đã push V2 → {url}")
    except Exception as e:
        print(f"⚠️  V2 lỗi: {e}")


# ── 4. Pull Prompts từ Prompt Hub ──────────────────────────────────────────
def pull_prompts_from_hub(client: Client) -> dict:
    """
    Tải 2 prompt từ LangSmith Prompt Hub.
    Fallback về template local nếu Hub không khả dụng.

    Gợi ý: client.pull_prompt(name) → ChatPromptTemplate

    Trả về: {name: ChatPromptTemplate}
    """
    prompts = {}

    # TODO hoàn thành: Pull PROMPT_V1_NAME từ Hub, fallback về local PROMPT_V1 nếu lỗi.
    try:
        prompts[PROMPT_V1_NAME] = client.pull_prompt(PROMPT_V1_NAME)
        print(f"↓ Đã pull '{PROMPT_V1_NAME}' từ Hub")
    except Exception as e:
        prompts[PROMPT_V1_NAME] = PROMPT_V1
        print(f"ℹ️  Dùng local fallback cho '{PROMPT_V1_NAME}': {e}")

    # TODO hoàn thành: Pull PROMPT_V2_NAME từ Hub, fallback về local PROMPT_V2 nếu lỗi.
    try:
        prompts[PROMPT_V2_NAME] = client.pull_prompt(PROMPT_V2_NAME)
        print(f"↓ Đã pull '{PROMPT_V2_NAME}' từ Hub")
    except Exception as e:
        prompts[PROMPT_V2_NAME] = PROMPT_V2
        print(f"ℹ️  Dùng local fallback cho '{PROMPT_V2_NAME}': {e}")

    return prompts


# ── 5. A/B Routing tất định ────────────────────────────────────────────────
def get_prompt_version(request_id: str) -> str:
    """
    Xác định prompt version dựa trên MD5 hash của request_id.

    Quy tắc: hash chẵn → PROMPT_V1_NAME | hash lẻ → PROMPT_V2_NAME
    TÍNH CHẤT: cùng request_id LUÔN cho cùng kết quả (deterministic).

    Gợi ý:
        hash_int = int(hashlib.md5(request_id.encode()).hexdigest(), 16)
        return PROMPT_V1_NAME if hash_int % 2 == 0 else PROMPT_V2_NAME
    """
    # TODO hoàn thành: Tính MD5 hash của request_id và chuyển thành số nguyên.
    hash_int = int(hashlib.md5(request_id.encode()).hexdigest(), 16)

    # TODO hoàn thành: Hash chẵn chọn V1, hash lẻ chọn V2.
    return PROMPT_V1_NAME if hash_int % 2 == 0 else PROMPT_V2_NAME


# ── 6. Traced A/B Query ────────────────────────────────────────────────────
# TODO hoàn thành: Decorator traceable tạo trace riêng cho từng A/B query.
@traceable(name="ab-rag-query", tags=["ab-test", "step2"])
def ask_ab(retriever, llm, prompt, question: str, version: str) -> dict:
    """
    Chạy RAG chain với prompt version được chọn bởi router.

    Bước:
      a) Retrieve top-3 docs từ retriever
      b) Ghép page_content thành context string
      c) Chạy (prompt | llm | StrOutputParser()).invoke({"context": ..., "question": ...})
      d) Trả về {"question": ..., "answer": ..., "version": ...}
    """
    # TODO hoàn thành: Retrieve top-3 docs từ retriever.
    docs = retriever.invoke(question)

    # TODO hoàn thành: Ghép page_content thành một context string.
    context = "\n\n".join(doc.page_content for doc in docs)

    # TODO hoàn thành: Chạy prompt → llm → parser với context và question.
    answer = (prompt | llm | StrOutputParser()).invoke({
        "context": context,
        "question": question,
    })

    # TODO hoàn thành: Trả về dict kết quả kèm version để log/trace rõ nhánh A/B.
    return {
        "question": question,
        "answer": answer,
        "version": version,
    }


# ── 7. Setup Vectorstore (tái sử dụng logic Bước 1) ───────────────────────
def setup_vectorstore():
    embeddings  = get_embeddings()
    text        = load_knowledge_base()
    chunks      = split_text(text)
    return build_vectorstore(chunks, embeddings)


# ── 8. Main ────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  Bước 2: Prompt Hub & A/B Routing")
    print("=" * 60)

    if not config.validate():
        sys.exit(1)

    # TODO hoàn thành: Tạo LangSmith Client với API key từ config.
    client = Client(api_key=config.LANGSMITH_API_KEY)

    # TODO hoàn thành: Push cả 2 prompts lên Hub.
    push_prompts_to_hub(client)

    # TODO hoàn thành: Pull cả 2 prompts từ Hub, nhận về dict name → prompt.
    prompts = pull_prompts_from_hub(client)

    # Tạo vectorstore, retriever và LLM
    vectorstore = setup_vectorstore()
    # TODO hoàn thành: Tạo retriever từ vectorstore, lấy k=3 docs.
    retriever   = vectorstore.as_retriever(search_kwargs={"k": 3})
    llm         = get_llm()

    # Chạy A/B routing cho tất cả câu hỏi
    v1_count, v2_count = 0, 0
    for i, question in enumerate(SAMPLE_QUESTIONS):
        request_id  = f"req-{i:04d}"

        # TODO hoàn thành: Lấy prompt key từ request_id qua deterministic router.
        version_key = get_prompt_version(request_id)
        version_tag = "v1" if version_key == PROMPT_V1_NAME else "v2"
        prompt      = prompts[version_key]

        # TODO hoàn thành: Gọi ask_ab() với đúng retriever, llm, prompt, question, version.
        result = ask_ab(retriever, llm, prompt, question, version_tag)

        if version_tag == "v1":
            v1_count += 1
        else:
            v2_count += 1
        print(f"[{i+1:02d}] [prompt-{version_tag}] {question[:55]}...")

    print(f"\n📊 Routing: V1={v1_count} câu | V2={v2_count} câu | Tổng={len(SAMPLE_QUESTIONS)}")
    print("✅ Bước 2 hoàn thành! Kiểm tra Prompt Hub và traces trên LangSmith.")


if __name__ == "__main__":
    main()
