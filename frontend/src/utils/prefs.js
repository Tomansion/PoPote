/**
 * The ten questions on a profile, in the order they are asked and shown.
 *
 * One definition for both screens: the form that fills them in and the member
 * page that reads them back. Keeping them here — rather than as markup in two
 * components — is what stops the page labelling an answer differently from the
 * question that produced it.
 *
 * The mix is deliberate. Half are the practical things you need to know before
 * cooking for someone (régime, allergies, alcool), and half exist so a profile
 * is worth opening at all. `key` matches the backend's ProfilePrefs field.
 */
export const PREF_QUESTIONS = [
  {
    key: 'diet',
    label: 'Mon régime',
    icon: 'mdi-leaf',
    placeholder: 'Je mange de tout, végétarien·ne…',
    suggestions: [
      'Je mange de tout',
      'Végétarien·ne',
      'Végétalien·ne',
      'Pescétarien·ne',
      'Sans gluten',
      'Sans lactose',
      'Halal',
      'Casher',
    ],
  },
  {
    key: 'allergies',
    label: 'Ce que je ne peux pas manger',
    icon: 'mdi-alert-circle-outline',
    placeholder: 'Allergies, intolérances…',
  },
  {
    key: 'dislikes',
    label: 'Ce que je n’aime pas',
    icon: 'mdi-emoticon-sick-outline',
    placeholder: 'Les olives, la coriandre…',
  },
  {
    key: 'alcohol',
    label: 'L’alcool et moi',
    icon: 'mdi-glass-wine',
    placeholder: 'Un verre de rouge et ça va…',
    suggestions: [
      'Je bois de tout',
      'Un verre, pas plus',
      'Bière uniquement',
      'Je ne bois pas d’alcool',
    ],
  },
  {
    key: 'spice',
    label: 'Le piment et moi',
    icon: 'mdi-chili-mild',
    placeholder: 'Doux, relevé, incendiaire ?',
    suggestions: ['Zéro piment', 'Doux', 'Relevé', 'Le plus fort possible'],
  },
  {
    key: 'cheese',
    label: 'Mon fromage préféré',
    icon: 'mdi-cheese',
    placeholder: 'Comté 24 mois, roquefort…',
  },
  {
    key: 'signature',
    label: 'Ma spécialité',
    icon: 'mdi-chef-hat',
    placeholder: 'Le plat que je réussis à tous les coups',
  },
  {
    key: 'guilty_pleasure',
    label: 'Mon péché mignon',
    icon: 'mdi-cupcake',
    placeholder: 'Ce que je mange debout devant le frigo',
  },
  {
    key: 'hated_veggie',
    label: 'Le légume que je fuis depuis l’enfance',
    icon: 'mdi-carrot',
    placeholder: 'Les épinards, soyons honnêtes',
  },
  {
    key: 'last_meal',
    label: 'Mon dernier repas sur terre',
    icon: 'mdi-silverware-variant',
    placeholder: 'Sans hésiter…',
  },
]

/** A full set of blank answers, for a profile that has never been filled in. */
export function blankPrefs() {
  return Object.fromEntries(PREF_QUESTIONS.map((q) => [q.key, '']))
}

/**
 * Only the questions this person actually answered.
 *
 * An empty answer is never shown: a member page listing seven blanks reads as
 * a broken form, while three filled-in lines read as a choice.
 */
export function answeredPrefs(prefs) {
  if (!prefs) return []
  return PREF_QUESTIONS.filter((q) => (prefs[q.key] ?? '').trim()).map((q) => ({
    ...q,
    answer: prefs[q.key].trim(),
  }))
}
