# Authorization Matrix

Protected application/backend operations must enforce permissions in the application or backend
layer. Bot and Mini App UI checks are only convenience guards.

| Operation | User | Operator | Super admin | Internal/service |
| --- | --- | --- | --- | --- |
| Create own ticket / add own client message | Allowed | N/A | N/A | Allowed via backend token |
| Submit feedback for own ticket | Allowed | N/A | N/A | Allowed via backend token |
| View operator queue | Denied | `ACCESS_OPERATOR` | `ACCESS_OPERATOR` | Allowed via backend token |
| View ticket workspace/details | Denied unless own client flow | `ACCESS_OPERATOR` | `ACCESS_OPERATOR` | Allowed via backend token |
| Reply to ticket | Denied | `ACCESS_OPERATOR` | `ACCESS_OPERATOR` | Allowed via backend token |
| Close as operator | Denied | `ACCESS_OPERATOR` | `ACCESS_OPERATOR` | Allowed via backend token |
| Assign / take / reassign / escalate | Denied | `ACCESS_OPERATOR` | `ACCESS_OPERATOR` | Allowed via backend token |
| Export ticket report | Denied | `ACCESS_OPERATOR` | `ACCESS_OPERATOR` | Allowed via backend token |
| AI assist / reply draft / macro suggestions | Denied | `ACCESS_OPERATOR` | `ACCESS_OPERATOR` | Allowed via backend token |
| Read/apply macros | Denied | `ACCESS_OPERATOR` | `ACCESS_OPERATOR` | Allowed via backend token |
| Manage categories | Denied | Denied | `ACCESS_ADMIN` | Allowed via backend token |
| Manage operators / invites | Denied | Denied | `MANAGE_OPERATORS` | Allowed via backend token |
| Analytics snapshot / export | Denied | `ACCESS_OPERATOR` | `ACCESS_OPERATOR` | Allowed via backend token |

Current permission primitives:

- `ACCESS_OPERATOR`: operator workspace, ticket work, exports, AI assist, macros, analytics.
- `ACCESS_ADMIN`: category/admin surfaces reserved for super admins.
- `MANAGE_OPERATORS`: operator directory and invite lifecycle reserved for super admins.

When adding a protected operation, add a negative authorization test that calls the
application/backend boundary, not only a Telegram or Mini App handler.
