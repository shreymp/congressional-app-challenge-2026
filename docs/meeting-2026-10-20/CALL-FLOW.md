# What happens when a call arrives

```mermaid
flowchart TD
    A[Someone calls the app's number] --> B[The app rings]
    B --> C{Answer?}
    C -->|No| D[Save a missed call and end the connection]
    C -->|Yes| E[Connect the call and show Analyzing]
    E --> F[Check the caller's voice]
    E --> G[Check the caller's words for scam language]
    F --> H[Show voice result or an honest uncertain / unavailable state]
    G --> I[Show the highest scam risk observed in this call]
    H --> J[User continues or ends the call]
    I --> J
    J --> K[Save call details for later review]
```

The user sees who is calling, a voice result, a separate scam warning, and large call controls. Call history preserves assessments. Optional transcript excerpts appear only in call details, after a flagged call, when the server option is enabled for previously consented controlled tests. No live transcript is displayed.

Current calling service supports incoming calls while the app is open. Outgoing calls use the phone's normal service and are not analyzed. The call-start notice and automatic consent gate are unfinished. A voice result is not identity verification. This diagram describes the production iPhone path; `frontendscreens/` is a simulated React prototype.
