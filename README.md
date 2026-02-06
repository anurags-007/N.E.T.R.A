# N.E.T.R.A. (Network Evidence Tracking & Record Analysis)

## 🚓 Police Intelligence & Cybercrime Investigation System

**N.E.T.R.A.** is a state-of-the-art, secure, and centralized portal designed for law enforcement agencies to streamline cybercrime investigations. It provides officers with advanced tools for case management, financial fraud tracking, and intelligence analytics, ensuring rapid response and data-driven decision-making.

---

### 🚀 Key Features

*   **🗂 Advanced Case Management**
    *   Digital FIR tracking with real-time status updates (Active, Pending, Closed).
    *   Categorized filing for Financial Fraud vs. Non-Financial Cyber Crime.
    *   Secure Evidence Locker for encrypted file storage.

*   **💰 Financial Intelligence Module**
    *   Specialized tracking for **Bank Accounts**, **UPI IDs** (Paytm/PhonePe), and **Crypto Wallets**.
    *   Automated NPCI request generation and transaction analysis.
    *   Link analysis to identify money mule networks.

*   **📡 Telecom & Cyber Tools**
    *   **IP Geo-Locator** & Domain Analysis.
    *   **Telecom Requests** portal for CDR/IPDR data acquisition.
    *   **Intelligence Analytics** dashboard for cross-case pattern matching.

*   **🛡️ Security & Compliance**
    *   **Role-Based Access Control (RBAC)** for secure hierarchy management.
    *   **Audit Logging**: Immutable logs of all officer actions for legal admissibility.
    *   Dark Mode interface optimized for 24/7 command center operations.

---

### 🛠️ Tech Stack

*   **Frontend**: HTML5, Vanilla JavaScript, Bootstrap 5 (Glassmorphism UI)
*   **Backend**: Python 3.x (FastAPI)
*   **Database**: SQLite (Lightweight & Portable)
*   **Security**: DOMPurify, Secure Session Management

---

### ⚡ Quick Start

#### Prerequisites
*   Python 3.8+ installed on your system.

#### Installation & Running
1.  **Clone/Download** the repository.
2.  **Open Terminal** in the project folder.
3.  **Run the automated script**:
    ```bash
    bash run.sh
    ```
    *This script automatically creates a virtual environment, installs dependencies, and starts the server.*

**Manual Setup:**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --port 8001 --reload
```

### 🌍 Access
*   **Dashboard**: `http://localhost:8001/frontend/index.html`
*   **Default Mode**: Evaluation / Local Development

