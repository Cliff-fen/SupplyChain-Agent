# SupplyChain Agent design system

Use semantic tokens from `src/styles/tokens.css` and primitives from this folder.
Business pages must not introduce new visual tokens or call Radix primitives directly.

- Controls use `Button`, `Input`, `Textarea`, `Badge`, and `IconButton`.
- Destructive actions use `ConfirmDialog`.
- Loading, empty, error, and permission states use the exported state primitives.
- Component styles are co-located CSS Modules; `styles.css` is a legacy migration file.
