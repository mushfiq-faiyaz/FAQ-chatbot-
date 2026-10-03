"""
test_e2e.py - End-to-End Answer Quality Test
=============================================
Calls answer_question() on each test case and prints the full bot response.
Run with:
    python test_e2e.py
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from rag_engine import answer_question

TEST_CASES = [
    ("Q1 - Wrong plan name (Business)",
     "How much do I save with annual billing on Business?"),

    ("Q2 - Wrong assumption (5 users Free plan)",
     "If I'm on the Free plan and go over 5 users, what happens?"),

    ("Q3 - Annual savings on Team",
     "What does annual billing save me on Team?"),

    ("Q4 - Free plan user count",
     "How many users does the Free plan include?"),

    ("Q5 - Prorated refund after 3 months on annual",
     "Can I get a refund on an annual plan after 3 months?"),

    ("Q6 - How to cancel",
     "How do I cancel?"),

    ("Q7 - Unrelated topic",
     "What is the best recipe for chocolate chip cookies?"),
]

SEP = "=" * 70

for label, question in TEST_CASES:
    print(SEP)
    print(f"  {label}")
    print(f"  Q: {question}")
    print(SEP)
    result = answer_question(question)
    if result.get("error") and result["error"] not in (None, "RATE_LIMIT"):
        print(f"[ERROR {result['error']}]", result["answer"])
    else:
        print(result["answer"])
    print()
