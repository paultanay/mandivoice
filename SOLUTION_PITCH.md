# MandiVoice

### Say the order. Check every line. Get a clear total.

At a kirana counter, an order may arrive in Hindi, English, or a mix of both, while the shopkeeper is already helping someone else. Re-entering that order takes time, and a missed quantity or price can leave the customer and shopkeeper disagreeing about the bill. A speech transcript helps, but it still leaves the shopkeeper to turn a paragraph into billable items.

MandiVoice turns a short spoken order into an editable bill draft. A shopkeeper records a voice note or chooses an audio file. Gnani Prisma transcribes it; Groq organizes the transcript into item names, quantities, units, prices, and any tax or adjustments the customer stated. The transcript stays visible beside the draft, so the shopkeeper can compare what was said with what the system understood.

The important design choice is to separate interpretation from arithmetic. The language model proposes fields; it does not calculate money. MandiVoice uses decimal arithmetic for line amounts, discounts, tax, and the total. It leaves missing values open for review, asks for clarification when a required detail is unclear, and requires the shopkeeper to check the draft before calculating. A Hindi read-back is available for supported orders, giving the shopkeeper another way to catch a mismatch.

This keeps the shopkeeper in control of the final bill. MandiVoice does not look up a price or tax rate and present it as fact. It works from the order and the values the shopkeeper confirms. The first version is deliberately focused on preparing and checking a bill draft; it does not take payment or keep bill history.

The current prototype supports audio recording and upload, an editable transcript, structured order drafts, review questions, GST and common bill adjustments, decimal totals, and Hindi read-back for supported drafts. Its regression suite covers the calculation and review flow, including examples in several Indian languages. That is useful development evidence, not a claim that speech recognition is perfect in every accent or noisy shop.

The next step is a small counter pilot. Compare order-entry time and correction rates with the shop’s usual process, and record when the draft asks for clarification or needs a human correction. The measure of success is straightforward: less retyping, visible uncertainty, and totals that match the values the shopkeeper approved.
