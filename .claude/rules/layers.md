# Layer Dependency Rules

- Domain layer (`domain/`): Python standard library only
- Application layer (`engine/`): Python standard library + domain layer only
- Infrastructure layer (`main.py`, `session.py`, `templates/`): All libraries allowed. May import from engine / domain
- Dependency direction: Infrastructure → Application → Domain (reverse dependencies prohibited)
