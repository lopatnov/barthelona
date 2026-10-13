---
paths:
  - "src/barthelona/ui/**"
---
# Streamlit UI rules (docs/architecture.md §17, ADR D-005)

- The UI is a thin client. It talks only to `var/app.sqlite` through `ui/client.py`:
  - it writes `runs`, `commands` and gate decisions;
  - it reads events and gates.

  It never imports the engine, LangGraph or the LLM gateway, and never starts threads or processes.
- Use multipage navigation with `st.navigation` / `st.Page`. Live views use `@st.fragment(run_every=1)` and read only events with `seq > last_seq`.
- `st.cache_resource` is used only for a read-only SQLite handle (`check_same_thread=False`, WAL).
- No secrets in `st.session_state`, widgets or logs. Show provider keys only as present/absent.
- The New request form fields:
  - dialect and target preset (unsupported presets disabled, with the reason);
  - mode, description (RU/UK/EN input accepted);
  - profile, cloud consent and allowed providers;
  - optional dollar budget (empty = uncapped, still metered); time and token limits (empty = profile default, never unlimited);
  - composition level (L0/L1/L2) and autopilot.
- Show which model actually served each role, fallbacks, provider health and spend per provider.
- UI text is English. Test page logic with `streamlit.testing.v1.AppTest`.
