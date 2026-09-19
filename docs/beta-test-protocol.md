# Apply Next: CS-Student Beta Test Protocol

**Goal**: Evaluate the first small CS-student beta of Apply Next (Issue #390) to understand how students use the recommendation queue to decide "what to apply to next".

This protocol ensures observations and feedback are comparable across participants. It separates human observation from product telemetry and is intentionally lightweight. We do not collect unnecessary sensitive personal information or use any external production analytics stack.

## Test Boundaries and Constraints

- **CS-First Beta**: The initial beta experience focuses exclusively on Computer Science students.
- **Privacy First**: Do not collect sensitive PII. Observations are anonymous or tied to a non-PII test ID.
- **No Production Analytics**: Relies on browser-local state (Saved, Applied, Hidden) and human observation.
- **Links**: Relates to the broader beta-readiness coordination issue.

## Test Flow

1. **Profile Setup**:
   - The participant fills out their profile (skills, location preferences, work authorization, etc.).
2. **Top 10 Review**:
   - The participant reviews the top 10 recommended internships presented by Apply Next.
3. **Actions (Apply, Hide, Save)**:
   - The participant takes action on the recommendations (marking them as Applied, Hidden, or Saved).
4. **Recommendation Replenishment**:
   - Observe how the queue replenishes as the participant acts on the Top 10 recommendations.
5. **Good/Bad Feedback**:
   - The participant provides feedback on whether a suggestion was "Good" or "Bad" and why.

## Minimum Human Observations to Record

During the test flow, the observer should record the following (without collecting PII):

*   **Confusion Points**: Where did the participant hesitate, ask questions, or seem unsure of what to do?
*   **Card Comprehension**: Did the participant understand the evidence and reasoning on the job card (e.g., why it matched their profile, readiness score, etc.)?
*   **Bad-Suggestion Reasons**: Why did the participant hide or mark a recommendation as bad?
*   **Application Intent/Action**: Did the participant actually intend to apply to the roles they marked as "Save" or "Apply"? Did they understand the difference between the job posting and the application destination?
*   **Exhaustion**: At what point did the participant feel "done" or overwhelmed by the queue?
*   **Obvious Dead/Inappropriate Recommendations**: Were any of the recommendations clearly broken, closed, or completely irrelevant despite the ranking?

## Post-Session Questions

Keep the post-session interview concise, focusing on the core value proposition.

1.  **"Did this help you figure out what to apply to next?"**
2.  **"What was the most surprising thing the queue recommended?"**
3.  **"Was there anything missing from the job cards that you needed to make a decision?"**
4.  **"How did this experience compare to how you normally look for internships?"**
