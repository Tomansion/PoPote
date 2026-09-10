/**
 * Display names for the aisle keys the backend produces.
 *
 * The keys are terse because they are stored on every ingredient of every
 * recipe ("f&l", "laitier"); a shopping list read at arm's length in a shop
 * wants the full word. The order is the backend's, which is roughly the order
 * you walk a supermarket — the list arrives already sorted that way.
 */
export const AISLE_LABELS = {
  viande: 'Viande',
  poisson: 'Poissonnerie',
  'f&l': 'Fruits & légumes',
  laitier: 'Crèmerie',
  épicerie: 'Épicerie',
  boulangerie: 'Boulangerie',
  surgelé: 'Surgelés',
  boisson: 'Boissons',
  autre: 'Autres',
}
