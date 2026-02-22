---
name: next-week
description: >
  Sends Vít a weekly planning email summarizing everything important from today through the end of next calendar week.
  Use this skill whenever the user asks for a "next week summary", "weekly briefing", "what's coming up", "send me my week",
  or anything that implies generating and emailing a personal weekly overview. Always use this skill — don't just answer
  in chat — when the intent is to prepare and send the weekly email.
---

# Next Week Skill

Generates and emails a weekly planning summary covering:
1. **📌 Now — Upcoming Rituals & Reminders** (from Notion Life OS › Now page)
2. **✈️ Travel — Open Todos & Next Trip** (from Notion Travel Hub child pages)
3. **🎭 Theatre Visits this week** (from BigQuery) + day-trip ideas from Notion Opera Day Trip db
4. **✅ General Todos** (open items from Now page relevant to the week)

---

## Step 0 — Define "next week"

"Next week" = from **today** (inclusive) through the **end of next calendar week** (the Sunday after the coming one), giving a window of 7–14 days depending on what day today is.

```python
from datetime import date, timedelta
today = date.today()
# Days until end of THIS calendar week (the coming Sunday)
days_until_this_sunday = (6 - today.weekday()) % 7
if days_until_this_sunday == 0:
    days_until_this_sunday = 7  # today is Sunday, so "this Sunday" = next Sunday
# End of NEXT calendar week = one full week beyond that
end_of_week = today + timedelta(days=days_until_this_sunday + 7)
```

Example: today is Sunday Feb 22 → this week ends Mar 1 → **next week ends Sun Mar 8** → window is Feb 22–Mar 8.
Example: today is Monday Feb 23 → this week ends Mar 1 → **next week ends Sun Mar 8** → window is Feb 23–Mar 8.

⚠️ IMPORTANT: The end date (Sunday) is INCLUSIVE. After filtering, always do a final explicit check: "are there any events on exactly end_of_week?" to avoid missing boundary-day items.

---

## Step 1 — Fetch Notion: 📌 Now page

Page ID: `30d1c31b-7fca-815a-85a1-c014f3a77795`

Fetch using `notion-fetch`. Extract:

- **Upcoming Rituals** table: pick rows where date falls within the next-week window OR within the next 30 days (show all within 30 days, mark those in the window with 🔔).
- **Open todos** (unchecked `[ ]` items) across all sections — group by section heading.
- **Active Experiments** — just list names + next review date if within 30 days.

---

## Step 2 — Fetch Notion: ✈️ Travel Hub

Travel Hub page ID: `30e1c31b-7fca-81eb-b993-c3a6c1c20893`

Get list of child trip pages, then fetch **each one**. For each trip page:

1. Parse the trip date from the title (e.g. "May 7–10", "Aug 18–26").
2. Count **open todos** (`[ ]`) vs **done todos** (`[x]`).
3. Flag as **urgent** if it has open todos AND the trip is within 90 days.
4. Identify the **next/soonest upcoming trip** (by start date).

In the email:
- **Next trip** section: name, dates, open todo count, and list the open todos.
- **Other trips with urgent items**: list trip name + open todo count + the actual open todos.
- Trips with no open todos: just mention them briefly.

> The Opera Day Trip database (`b7a84b72-bf70-4696-9948-9e193e067f68`) lives inside Travel Hub but is handled separately in Step 4.

---

## Step 3 — Fetch BigQuery: Theatre visits this week

```sql
SELECT datum, program, misto, den_tydne, pozn_2, pozn_3, kdo, listky
FROM `fivetran-connector-sdk.google_sheets.opery_divadla_dovolene`
WHERE datum IS NOT NULL AND program IS NOT NULL
ORDER BY _row
```

Dates are stored as Czech-format strings (`"27.6.2024"`, `"8.5.2026"`, etc.) — parse them carefully (DD.MM.YYYY). Filter to events within the next-week window (today inclusive through end_of_week inclusive).

⚠️ IMPORTANT: The end date (Sunday) is INCLUSIVE. After filtering, always do a final explicit check: "are there any events on exactly end_of_week?" to avoid missing boundary-day items.

Fields to display: date, day of week (`den_tydne`), venue (`misto`), performance (`program`), time (`pozn_2`), who (`kdo`), tickets booked (`listky` — true/false).

---

## Step 4 — Fetch Notion: Opera Day Trip ideas for theatre cities

Query the Opera Day Trip database (`collection://09f43d65-cc7c-4a10-bc53-6773bcefeb88`) for cities that appear in this week's theatre visits (Step 3).

Map BigQuery `misto` values to database `City` options:
- "Londyn" → "London"
- "Dresden" → "Dresden"
- "Wien" → "Wien"
- "Berlin DO" → "Berlin"
- "Leipzig" / "Lipsko GHO" → "Leipzig"
- "Verona" → "Verona"
- Prague-based venues (Praha kino, ND, Turnov, SO, Liberec, etc.): skip — no day-trip ideas needed

For each matched city, fetch ONLY items where Status = "Want to visit" — explicitly exclude "Visited" items. Group by category. Keep it brief — 3–5 highlights per city.

---

## Step 5 — Compose and send email via osascript

### Email metadata
- **To:** vit.spinka@hey.com
- **Subject:** 📅 Next Week — {start_date} to {end_date}
- **Send via:** osascript (see template below)

### Formatting rules
- Plain text only — NO HTML. HTML will NOT render.
- Use Unicode/emoji extensively for structure and visual hierarchy.
- Use `─────────────────────` divider lines between sections.
- Use indented bullets with `  •` or `  →` for sub-items.
- Dates: write as "Mon Feb 23" not ISO.

### Email structure

```
📅 NEXT WEEK — Sun Feb 22 → Sun Mar 8
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📌 NOW — UPCOMING REMINDERS
─────────────────────────────
🔔 [items this week]
⏳ [items in next 30 days]

📌 NOW — OPEN TODOS
─────────────────────
[grouped by section, e.g. 💰 Financial, 🤖 AI & Tools, etc.]

✈️ NEXT TRIP: [trip name]
─────────────────────────────
📆 [dates] | [family members]
✅ [X done] / ⬜ [Y open]
Open todos:
  → [todo 1]
  → [todo 2]
  ...

✈️ OTHER TRIPS — URGENT ITEMS
─────────────────────────────
[trip name] ([dates]) — [N open todos]
  → [todo 1]
  ...

🎭 THEATRE THIS WEEK
─────────────────────
[date] [day] — [program] @ [misto]
  🕐 [time] | 🎟️ [tickets: yes/no] | 👤 [kdo]
  📝 [pozn_3 if any]
  🗺️ Day-trip ideas for [City]: [brief list]

[if no theatre this week: "No theatre visits this week."]
```

### osascript template

```applescript
tell application "Mail"
    set newMessage to make new outgoing message with properties {subject:"SUBJECT_HERE", content:"BODY_HERE", visible:false}
    tell newMessage
        make new to recipient at end of to recipients with properties {address:"vit.spinka@hey.com"}
    end tell
    send newMessage
end tell
```

Replace `SUBJECT_HERE` and `BODY_HERE`. The body must be plain text — escape any double quotes as `\"` and newlines as `\n` within the AppleScript string.

---

## Error handling

- If a trip page can't be fetched, note it in the email as "⚠️ Could not fetch [trip name]".
- If BigQuery returns no upcoming theatre events, write "No theatre visits this week."
- If Opera Day Trip db has no matches for a city, skip that city's day-trip section.
- Dates that can't be parsed (range formats like "7.-10.5.", "25.4-3.5.") — try to extract the start date; if impossible, skip filtering but mention the event if the month matches.

---

## Notes on date parsing (Czech BigQuery data)

The `datum` field is messy. Examples:
- `"8.5.2026"` → May 8, 2026
- `"7.-10.5."` → range, start May 7 (assume current year if no year)
- `"srpen 2024"` → month only, skip
- `"zari 12-22"` → range, skip precise filtering
- `"3.6.2026"` → June 3, 2026

Best-effort parse: try `DD.MM.YYYY` first; then `DD.MM.` with current year; then skip if unparseable.
