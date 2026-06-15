/** Single soft gradient that slowly shifts — sits behind all glass panels. */
export function AppBackground() {
  return (
    <div className="moving-gradient-bg pointer-events-none fixed inset-0 -z-10" aria-hidden />
  );
}
