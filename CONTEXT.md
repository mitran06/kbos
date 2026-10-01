# KBOS

KBOS is a voice-first ticketing system for a small factory floor. Workers report, query and resolve machine problems by talking to KB, so every shift inherits an unambiguous record of what is still open.

## Language

### People

**Operator**:
A person who runs a Machine during a Shift and reports problems with it.
_Avoid_: worker, user

**Supervisor**:
A person who oversees every Machine on a Shift and may reassign or close any Ticket.

**Maintenance Technician**:
A person who works on and closes the Tickets assigned to them.
_Avoid_: mechanic, fitter

**Admin**:
A person who monitors and moderates all Tickets from the web dashboard and does not use the mobile app.
_Avoid_: manager

**KB**:
The voice assistant inside the KBOS app.
_Avoid_: bot, agent, Jarvis

### Tickets

**Ticket**:
A record of one problem on a Machine that needs attention, from the first report until it is Closed.
_Avoid_: issue, complaint, observation, fault report

**Draft**:
A Ticket that is being dictated to KB and has not been filed yet. It becomes a Ticket only when the Reporter approves it.
_Avoid_: pending ticket, form

**Reporter**:
The person who filed a Ticket.

**Assignee**:
A person responsible for acting on a Ticket. A Ticket may have several.

**Severity**:
How urgent a Ticket is: Critical (production stopped or safety risk), High (getting worse, a stop is likely), Medium or Low.

**Status**:
Where a Ticket is in its life: Open, In Progress, Monitoring or Closed.

**Monitoring**:
The Status of a Ticket that someone has looked at but that is not confirmed fixed. It always has an owner and a next-check time, and it never means resolved.
_Avoid_: checked, under observation

**Check**:
A recorded inspection on a Ticket: what was checked, what was found, who did it, and when. Every Status change carries one.
_Avoid_: note, comment, update

**Unclear Check**:
A Check that doesn't say what was checked or what was found, such as a bare "checked". It is recorded as given but permanently flagged, so no later shift mistakes it for a fix.
_Avoid_: vague note

**Related Ticket**:
Another Ticket on the same Machine with a similar symptom, linked so that a recurring problem reads as one story.

### Plant

**Machine**:
A piece of production equipment that Tickets are filed against. It is identified by a short floor code such as "4B".
_Avoid_: asset, equipment, device

**Telemetry Snapshot**:
A Machine's readings (vibration, temperature, load, output against target) frozen at the moment a Ticket is filed.

**Production Target**:
The output a Machine is expected to produce during a Shift.

**Shorthand Glossary**:
The plant's list of local abbreviations and their meanings (e.g. "TC" = tool change), which KB uses to understand what workers say.

### Shifts

**Shift**:
A fixed 12-hour working period that each person belongs to: Day (08:00–20:00) or Night (20:00–08:00). Logging into the app starts your shift and logging out ends it.
_Avoid_: session, duty

**Shift Brief**:
KB's spoken summary, given when a person starts their shift, of what is open and what changed since their last shift.

**Handover**:
KB's conversation when a person ends their shift. It records the current state of every open Ticket that person touched.
