import asyncio
import uuid

from vanna.core.tool import ToolContext
from vanna.core.user import User
from vanna_setup import agent_memory

# Each tuple: (natural-language question, correct SQL)
SEED_PAIRS = [
    # Patient related queries
    (
        "How many patients do we have?",
        "SELECT COUNT(*) AS total_patients FROM patients;"
    ),
    (
        "List all patients from New York",
        "SELECT first_name, last_name, email, phone FROM patients WHERE city = 'New York';"
    ),
    (
        "How many female patients are registered?",
        "SELECT COUNT(*) AS female_patients FROM patients WHERE gender = 'F';"
    ),
    (
        "Which city has the most patients?",
        "SELECT city, COUNT(*) AS patient_count FROM patients "
        "GROUP BY city ORDER BY patient_count DESC LIMIT 1;"
    ),
    (
        "List patients who visited more than 3 times",
        "SELECT p.first_name, p.last_name, COUNT(a.id) AS visit_count "
        "FROM patients p JOIN appointments a ON a.patient_id = p.id "
        "GROUP BY p.id HAVING visit_count > 3 ORDER BY visit_count DESC;"
    ),

    # Doctor related queries
    (
        "List all doctors and their specializations",
        "SELECT name, specialization, department FROM doctors ORDER BY specialization, name;"
    ),
    (
        "Which doctor has the most appointments?",
        "SELECT d.name, d.specialization, COUNT(a.id) AS appointment_count "
        "FROM doctors d JOIN appointments a ON a.doctor_id = d.id "
        "GROUP BY d.id ORDER BY appointment_count DESC LIMIT 1;"
    ),

    # Appointment related queries
    (
        "How many appointments are there by status?",
        "SELECT status, COUNT(*) AS count FROM appointments GROUP BY status;"
    ),
    (
        "Show me appointments for last month",
        "SELECT a.id, p.first_name, p.last_name, d.name AS doctor, a.appointment_date, a.status "
        "FROM appointments a "
        "JOIN patients p ON p.id = a.patient_id "
        "JOIN doctors d ON d.id = a.doctor_id "
        "WHERE strftime('%Y-%m', a.appointment_date) = "
        "strftime('%Y-%m', date('now', '-1 month'));"
    ),
    (
        "How many cancelled appointments were there last quarter?",
        "SELECT COUNT(*) AS cancelled_count FROM appointments "
        "WHERE status = 'Cancelled' "
        "AND appointment_date >= date('now', '-3 months');"
    ),

    # Financial related queries
    (
        "What is the total revenue?",
        "SELECT SUM(total_amount) AS total_revenue FROM invoices;"
    ),
    (
        "Show revenue by doctor",
        "SELECT d.name, d.specialization, SUM(i.total_amount) AS total_revenue "
        "FROM invoices i "
        "JOIN appointments a ON a.patient_id = i.patient_id "
        "JOIN doctors d ON d.id = a.doctor_id "
        "GROUP BY d.id ORDER BY total_revenue DESC;"
    ),
    (
        "Show unpaid invoices",
        "SELECT p.first_name, p.last_name, i.invoice_date, i.total_amount, i.paid_amount, i.status "
        "FROM invoices i JOIN patients p ON p.id = i.patient_id "
        "WHERE i.status IN ('Pending', 'Overdue') ORDER BY i.invoice_date;"
    ),
    (
        "Top 5 patients by total spending",
        "SELECT p.first_name, p.last_name, SUM(i.total_amount) AS total_spent "
        "FROM invoices i JOIN patients p ON p.id = i.patient_id "
        "GROUP BY p.id ORDER BY total_spent DESC LIMIT 5;"
    ),

    # Time-based queries
    (
        "Show monthly appointment count for the past 6 months",
        "SELECT strftime('%Y-%m', appointment_date) AS month, COUNT(*) AS appointment_count "
        "FROM appointments "
        "WHERE appointment_date >= date('now', '-6 months') "
        "GROUP BY month ORDER BY month;"
    ),
]


async def seed():
    # Build a minimal ToolContext required by save_tool_usage()
    seed_user = User(
        id="seed-script",
        email="seed@clinic.local",
        group_memberships=["admin"],
    )
    ctx = ToolContext(
        user=seed_user,
        conversation_id=f"seed-{uuid.uuid4().hex[:8]}",
        request_id=f"req-{uuid.uuid4().hex[:8]}",
        agent_memory=agent_memory,
    )

    saved = 0
    for question, sql in SEED_PAIRS:
        try:
            await agent_memory.save_tool_usage(
                question=question,
                tool_name="run_sql",
                args={"sql": sql},
                context=ctx,
                success=True,
            )
            print(f"  Seeded: {question[:70]}")
            saved += 1
        except Exception as exc:
            print(f" Failed ({exc}): {question[:60]}")

    print(f"\n Seeded {saved}/{len(SEED_PAIRS)} Q→SQL pairs into DemoAgentMemory.")
    print("   Agent memory will use these as few-shot examples for similar questions.")


if __name__ == "__main__":
    asyncio.run(seed())
