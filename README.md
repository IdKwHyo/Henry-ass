# 🧠 Henry - Your Gemini-Powered Calendar Assistant

**Henry** is an intelligent calendar assistant built with **Flask**, **Gemini 1.5 Pro**, and the **Google Calendar API**. It helps users create, view, and manage events using natural language — and provides smart schedule insights with AI.

---

## ✨ Features

- 🔐 Google OAuth 2.0 Login
- 🧾 Natural language event parsing via Gemini 1.5 Pro
- 📅 Google Calendar integration (view, create, delete events)
- 🧠 Smart assistant replies about your schedule
- 🌐 Fully API-based, ready for frontend integration

---

## 📦 Tech Stack

- **Backend**: Flask (Python)
- **AI**: Google Gemini 1.5 Pro (via `google-generativeai`)
- **OAuth & Calendar API**: `google-auth`, `google-auth-oauthlib`, `google-api-python-client`
- **Environment**: Python 3.10+, `dotenv` for config management

---

## 🔐 Setup & Run (Local)

### 1. Clone the repo
```bash
git clone https://github.com/your-username/Henry-ass.git
cd Henry-ass
