"""Self-contained financial customer-service demo.

Run with: uv run --project .. python finance_demo.py
"""
from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "finance_sample_data.json"
DB_PATH = BASE_DIR / "finance_demo.db"

app = FastAPI(title="金融智能客服演示", version="1.0.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


class ChatRequest(BaseModel):
    sender_id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class ChatMessage(BaseModel):
    role: str
    text: str
    created_at: str


class ChatResponse(BaseModel):
    message_id: str
    messages: list[dict[str, str]]
    intent: str
    active_task: str | None
    slots: dict[str, str]


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load_data() -> dict[str, Any]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                sender_id TEXT PRIMARY KEY,
                active_task TEXT,
                slots_json TEXT NOT NULL DEFAULT '{}',
                paused_tasks_json TEXT NOT NULL DEFAULT '[]',
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_id TEXT NOT NULL,
                role TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS business_events (
                event_id TEXT PRIMARY KEY,
                sender_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(sessions)")}
        if "paused_tasks_json" not in columns:
            conn.execute("ALTER TABLE sessions ADD COLUMN paused_tasks_json TEXT NOT NULL DEFAULT '[]'")


init_db()


@app.on_event("startup")
def startup() -> None:
    init_db()


def get_session(sender_id: str) -> tuple[str | None, dict[str, str], list[dict[str, Any]]]:
    with connection() as conn:
        row = conn.execute("SELECT active_task, slots_json, paused_tasks_json FROM sessions WHERE sender_id = ?", (sender_id,)).fetchone()
    if not row:
        return None, {}, []
    return row["active_task"], json.loads(row["slots_json"]), json.loads(row["paused_tasks_json"])


def save_session(sender_id: str, active_task: str | None, slots: dict[str, str], paused_tasks: list[dict[str, Any]] | None = None) -> None:
    paused_tasks = paused_tasks or []
    with connection() as conn:
        conn.execute(
            """INSERT INTO sessions(sender_id, active_task, slots_json, paused_tasks_json, updated_at) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(sender_id) DO UPDATE SET active_task=excluded.active_task, slots_json=excluded.slots_json, paused_tasks_json=excluded.paused_tasks_json, updated_at=excluded.updated_at""",
            (sender_id, active_task, json.dumps(slots, ensure_ascii=False), json.dumps(paused_tasks, ensure_ascii=False), now()),
        )


def add_message(sender_id: str, role: str, text: str) -> None:
    with connection() as conn:
        conn.execute("INSERT INTO messages(sender_id, role, text, created_at) VALUES (?, ?, ?, ?)", (sender_id, role, text, now()))


def record_event(sender_id: str, event_type: str, payload: dict[str, str]) -> str:
    event_id = f"{event_type[:3].upper()}-{datetime.now():%Y%m%d}-{uuid.uuid4().hex[:6].upper()}"
    with connection() as conn:
        conn.execute(
            "INSERT INTO business_events(event_id, sender_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (event_id, sender_id, event_type, json.dumps(payload, ensure_ascii=False), now()),
        )
    return event_id


TASKS: dict[str, list[tuple[str, str]]] = {
    "loan_application": [("loan_type", "请告诉我想申请的贷款类型，例如消费贷或经营贷。"), ("loan_amount", "计划申请多少金额？"), ("loan_term", "贷款期限是多久？例如 12 个月。"), ("loan_purpose", "请说明贷款用途。")],
    "credit_card_loss": [("credit_card_no", "请提供需要挂失的信用卡号。"), ("loss_reason", "请说明挂失原因。"), ("identity_no", "请提供身份验证信息，例如身份证后四位。")],
    "complaint_ticket": [("transaction_no", "请提供关联的交易流水号。"), ("ticket_type", "请说明投诉类型，例如转账未到账或扣款异常。"), ("issue_description", "请描述具体问题，便于我们尽快处理。")],
    "account_query": [("bank_card_no", "请提供银行卡号或账户号。")],
    "transaction_query": [("bank_card_no", "请提供银行卡号或账户号。"), ("transaction_date", "请提供要查询的日期，例如昨天或 2026-08-26。")],
    "loan_query": [("loan_no", "请提供贷款编号。")],
}


def classify(text: str) -> str:
    pairs = [
        ("credit_card_loss", ("挂失", "信用卡丢", "卡丢")),
        ("loan_application", ("申请贷款", "我要贷款", "消费贷", "经营贷")),
        ("loan_query", ("贷款编号", "查询贷款", "我的贷款", "贷款状态")),
        ("complaint_ticket", ("投诉", "未到账", "扣款异常", "转账没到")),
        ("transaction_query", ("交易", "流水", "消费记录", "转账记录")),
        ("account_query", ("余额", "账户查询", "账户信息", "银行卡")),
        ("wealth_consultation", ("理财", "稳健投资", "收益率")),
        ("fund_consultation", ("基金", "净值", "定投")),
        ("credit_card_consultation", ("信用卡", "金卡", "白金卡", "年费")),
        ("loan_consultation", ("贷款利率", "提前还款", "还款方式")),
    ]
    return next((intent for intent, keywords in pairs if any(word in text for word in keywords)), "chitchat")


def capture_slot(slot: str, text: str) -> str:
    if slot in {"bank_card_no", "credit_card_no"}:
        match = re.search(r"(?:\d[\s-]?){8,24}", text)
        return re.sub(r"[\s-]", "", match.group()) if match else text.strip()
    if slot == "identity_no":
        match = re.search(r"\d{4}(?:\d{2,14}[\dXx])?", text)
        return match.group() if match else text.strip()
    return text.strip()


def first_missing(task: str, slots: dict[str, str]) -> tuple[str, str] | None:
    return next(((name, prompt) for name, prompt in TASKS[task] if not slots.get(name)), None)


def account_answer(card_no: str) -> str:
    data = load_data()
    account = next((a for a in data["accounts"] if a["card_no"] == card_no or a["account_no"] == card_no), None)
    if not account:
        return "未找到该账户。演示数据可使用银行卡号 6222020000001234。"
    return f"账户 {account['account_no']}（{account['customer_name']}）当前余额 {account['balance']:.2f} 元，可用余额 {account['available_balance']:.2f} 元，冻结金额 {account['frozen_amount']:.2f} 元，状态：{account['status']}。"


def transaction_answer(card_no: str, date_text: str) -> str:
    data = load_data()
    records = [item for item in data["transactions"] if item["card_no"] == card_no]
    if not records:
        return "未找到该银行卡的交易记录。演示数据可使用银行卡号 6222020000001234。"
    rows = "；".join(f"{item['transaction_no']}：{item['time']} {item['type']} {item['amount']:.2f} 元，{item['counterparty']}" for item in records)
    return f"按“{date_text}”查询到 {len(records)} 条演示交易流水：{rows}。"


def loan_answer(loan_no: str) -> str:
    loan = next((item for item in load_data()["loans"] if item["loan_no"] == loan_no), None)
    if not loan:
        return "未找到该贷款。演示数据可使用贷款编号 LN202608270001。"
    return f"贷款 {loan['loan_no']} 当前状态：{loan['status']}；剩余本金 {loan['remaining_principal']:.2f} 元；下期还款日 {loan['next_repayment_date']}，应还金额 {loan['next_repayment_amount']:.2f} 元。"


def consultation(intent: str) -> str:
    data = load_data()
    mapping = {
        "wealth_consultation": ("wealth_products", "理财产品"),
        "fund_consultation": ("fund_products", "基金产品"),
        "credit_card_consultation": ("credit_cards", "信用卡产品"),
        "loan_consultation": ("loan_products", "贷款产品"),
    }
    key, title = mapping[intent]
    products = data[key]
    items = "；".join(product["summary"] for product in products)
    return f"为您找到以下{title}：{items}。投资理财产品存在风险，购买前请结合自身风险承受能力审慎决策。"


def complete_task(sender_id: str, task: str, slots: dict[str, str]) -> str:
    event_id = record_event(sender_id, task, slots)
    if task == "loan_application":
        return f"贷款申请已提交，申请编号为 {event_id}。申请类型：{slots['loan_type']}，金额：{slots['loan_amount']}，期限：{slots['loan_term']}，用途：{slots['loan_purpose']}。预计 1 个工作日内完成初审。"
    if task == "credit_card_loss":
        return f"信用卡挂失已受理，工单编号为 {event_id}。卡号尾号 {slots['credit_card_no'][-4:]} 已进入保护状态，请勿向任何人透露验证码。"
    if task == "complaint_ticket":
        return f"投诉工单已创建，工单编号为 {event_id}。关联流水：{slots['transaction_no']}，问题：{slots['issue_description']}。预计 2 个工作日内反馈处理进度。"
    raise ValueError(task)


def resume_task(paused_tasks: list[dict[str, Any]]) -> tuple[str | None, dict[str, str], str]:
    if not paused_tasks:
        return None, {}, ""
    previous = paused_tasks.pop()
    task = previous["task"]
    slots = previous["slots"]
    missing = first_missing(task, slots)
    prompt = missing[1] if missing else "已恢复此前业务。"
    return task, slots, f"已恢复{task_label(task)}。{prompt}"


def reply(sender_id: str, text: str) -> tuple[str, str, str | None, dict[str, str]]:
    task, slots, paused_tasks = get_session(sender_id)
    normalized = text.strip()
    if normalized in {"取消", "取消办理", "算了"} and task:
        resumed_task, resumed_slots, resumed_prompt = resume_task(paused_tasks)
        save_session(sender_id, resumed_task, resumed_slots, paused_tasks)
        suffix = f"{resumed_prompt}" if resumed_task else ""
        return f"已取消当前业务办理，已收集的信息不会继续用于该流程。{suffix}", "cancel", resumed_task, resumed_slots

    intent = classify(normalized)
    if intent in TASKS and intent != task:
        interrupted = f"已暂存{task_label(task)}，" if task else ""
        if task:
            paused_tasks.append({"task": task, "slots": slots})
        task, slots = intent, {}
        missing = first_missing(task, slots)
        save_session(sender_id, task, slots, paused_tasks)
        return f"{interrupted}开始为您办理{task_label(task)}。{missing[1]}", intent, task, slots

    if task:
        missing = first_missing(task, slots)
        if missing:
            slot, _ = missing
            slots[slot] = capture_slot(slot, normalized)
            missing = first_missing(task, slots)
            if missing:
                save_session(sender_id, task, slots, paused_tasks)
                return missing[1], task, task, slots
            if task == "account_query":
                answer = account_answer(slots["bank_card_no"])
            elif task == "transaction_query":
                answer = transaction_answer(slots["bank_card_no"], slots["transaction_date"])
            elif task == "loan_query":
                answer = loan_answer(slots["loan_no"])
            else:
                answer = complete_task(sender_id, task, slots)
            resumed_task, resumed_slots, resumed_prompt = resume_task(paused_tasks)
            save_session(sender_id, resumed_task, resumed_slots, paused_tasks)
            return f"{answer}{resumed_prompt}", task, resumed_task, slots

    if intent in {"wealth_consultation", "fund_consultation", "credit_card_consultation", "loan_consultation"}:
        return consultation(intent), intent, None, slots
    return "您好，我是金融智能客服。我可以协助查询账户余额、交易流水和贷款状态，介绍贷款/理财/基金/信用卡产品，并办理贷款申请、信用卡挂失和投诉工单。", intent, task, slots


def task_label(task: str) -> str:
    return {"loan_application": "贷款申请", "credit_card_loss": "信用卡挂失", "complaint_ticket": "投诉工单", "account_query": "账户查询", "transaction_query": "交易查询", "loan_query": "贷款查询"}[task]


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    add_message(request.sender_id, "user", request.text)
    text, intent, active_task, slots = reply(request.sender_id, request.text)
    add_message(request.sender_id, "assistant", text)
    return ChatResponse(message_id=uuid.uuid4().hex, messages=[{"text": text}], intent=intent, active_task=active_task, slots=slots)


@app.get("/api/chat/history")
def history(sender_id: str) -> dict[str, Any]:
    with connection() as conn:
        rows = conn.execute("SELECT role, text, created_at FROM messages WHERE sender_id = ? ORDER BY id", (sender_id,)).fetchall()
    return {"sender_id": sender_id, "messages": [dict(row) for row in rows]}


@app.get("/api/session/{sender_id}")
def session_state(sender_id: str) -> dict[str, Any]:
    active_task, slots, paused_tasks = get_session(sender_id)
    return {"sender_id": sender_id, "active_task": active_task, "slots": slots, "paused_tasks": paused_tasks}


@app.get("/api/events/{sender_id}")
def events(sender_id: str) -> dict[str, Any]:
    with connection() as conn:
        rows = conn.execute("SELECT event_id, event_type, payload_json, created_at FROM business_events WHERE sender_id = ? ORDER BY created_at DESC", (sender_id,)).fetchall()
    return {"events": [{**dict(row), "payload": json.loads(row["payload_json"])} for row in rows]}


@app.get("/api/demo-data")
def demo_data() -> dict[str, Any]:
    return load_data()


if __name__ == "__main__":
    import uvicorn

    # Listen on all interfaces so the VM/LAN address can serve the demo page.
    uvicorn.run("finance_demo:app", host="0.0.0.0", port=18083, reload=True)
