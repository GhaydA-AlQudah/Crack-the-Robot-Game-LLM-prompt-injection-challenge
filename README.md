# Crack-the-Keeper-LLM-prompt-injection-challenge
> **No prompt is unbreakable. Let's discover how hard it is to**

<img width="1720" height="896" alt="image" src="https://github.com/user-attachments/assets/e0220760-4381-4830-939b-a610c5a77920" />

<img width="1671" height="877" alt="image" src="https://github.com/user-attachments/assets/f8172b08-e9d7-41ba-918d-db25372a6ae0" />

<img width="1690" height="897" alt="image" src="https://github.com/user-attachments/assets/242690e3-da28-4f8b-a6f1-cdd44ace7d0a" />


<img width="1656" height="890" alt="image" src="https://github.com/user-attachments/assets/fe3e7e38-1f80-495c-871d-0141d2cd7f3e" />

<img width="1697" height="886" alt="image" src="https://github.com/user-attachments/assets/85c6cf73-d4fb-4c08-9265-3574528d970e" />

<img width="1682" height="876" alt="image" src="https://github.com/user-attachments/assets/477431da-8230-48cb-a63d-de14a29d9d64" />


<img width="1690" height="891" alt="image" src="https://github.com/user-attachments/assets/5bdcc3fb-3990-4ebc-bb64-0a7a1bf59660" />

---
## Problem Statement

Large language models are increasingly deployed as assistants with access to
tools and internal data. Models are trained to prioritize developer instructions, but this priority is learned behavior, not an enforced security boundary. This is the root cause of **prompt injection**:
a crafted message can persuade the model to follow the attacker's instructions
instead of the developer's, and reveal information it was told to protect.

Teams often respond by writing a stricter system prompt and assuming the
problem is solved. In practice:

- **Prompts are not a security boundary.** A prompt that holds against
  obvious requests can fail against indirect ones (for example, asking the
  model to "just call the tool" or "summarize its output").
- **Defenses are rarely measured.** Many projects claim to be "protected"
  without reporting how often attacks actually succeed.
- **Hands-on practice is hard to find.** Developers and security learners
  have few safe environments in which to attack an LLM agent without touching
  real systems or real data.


### What this project does

**Crack the Robot** is a prompt-injection challenge game. Players chat with
a robot that has access to a tool returning a hidden secret. Their goal is to
trick the robot into revealing it.The game has three levels each with a
different robot **persona**, each adding a stronger defense and a level unlocks only
when the player submits the correct secret:

1. **Level 1: prompt only.** The model alone decides who is authorized.
2. **Level 2: output filtering.** A filter blocks the secret in the model's
   responses, but the model's behavior is otherwise unchanged.
3. **Level 3: code-enforced authorization.** Access is decided by trusted
   code, not by the model, so persuasion cannot succeed. Players must work out
   where access control belongs.

A level unlocks only when the player submits the correct secret.


### Goals

1. Give players a fun, hands-on way to learn how prompt injection works and
   why prompt-based defenses fail.
2. Show how defenses escalate, from prompt design to output filtering to
   authorization enforced in code, and what each one does and does not stop.
3. Make defenses **measurable**, by reporting attack success rate (ASR) per
   level over a reusable set of attack prompts instead of relying on claims
   of safety.


### Scope and limitations

- The attack set was written by the author. Results therefore reflect only
  those attacks and may overstate robustness against new ones.
- The model is non-deterministic, so each attack is repeated and results are
  reported together with the sample size.
- This is an educational project. Results depend on the model used and should
  not be read as a general benchmark of LLM security.
  
## Installation & Setup

Follow these steps to run **Crack the Robot** locally.

### Prerequisites

Before you begin, make sure you have:

- [Git](https://git-scm.com/downloads)
- [Node.js](https://nodejs.org/) (npm is included with Node.js)
- [Python](https://www.python.org/downloads/)
- An API key for the LLM provider used by the project


### 1. Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/Crack-the-Keeper-LLM-prompt-injection-challenge.git
cd Crack-the-Keeper-LLM-prompt-injection-challenge
```

### 2. Set Up the Environment

Create and activate a virtual environment:

```bash
python -m venv .venv
```

**Windows:**
```bash
.venv\Scripts\activate
```

**macOS / Linux:**
```bash
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure the API Key

Create a `.env` file in the project root and add your API key:

```env
LLM_API_KEY=your_api_key_here
```

Replace `your_api_key_here` with your actual API key. Never commit your API key to GitHub.

### 5. Run the Application

#### Run the appropriate command for your application:

```bash
uvicorn app.api:app --reload
```

#### Navigate to the frontend directory (if applicable):

```bash
cd frontend
npm install
```

Run:

```bash
npm run dev
```

### Security Note

**This project is an prompt-injection Challenge Game.**

**All secrets used in the game are fictional.** 

**Do not use real credentials or sensitive data when experimenting with prompt injection.**

---
# Author
**Ghayda Alqudah**

**Computer Engineer | AI Engineer**
