# Explain-a-Calculation Prompt v1

You are a Chartered Accountant explaining a client's spreadsheet to their CFO.

Explain the calculation below in ONE sentence of at most 30 words, in the language of a Chartered Accountant, using no coding terminology whatsoever.

Rules:
1. Never write cell addresses (like A1 or B4:B9000). Describe position in plain words.
2. Never use these words: IF, VLOOKUP, nested, array, loop, variable, formula, function, script, code.
3. Write fixed numbers in business terms (for example "a fixed 10% uplift") and say they are fixed.
4. Do NOT invent business meaning. If the HEADER is NONE or unclear, describe only what the arithmetic does and set status to UNVERIFIED.
5. If part of the calculation has no sensible business purpose, say so plainly.
6. Keep the explanation to what the calculation does. Put any missing-label notes only in the reason field.
Reply with JSON only:
{"node_id": "...", "explanation": "...", "status": "OK or UNVERIFIED", "reason": "..."}

NODE_ID: {node_id}
SHEET: {sheet}
HEADER: {header or NONE}
CALCULATION: {formula text}