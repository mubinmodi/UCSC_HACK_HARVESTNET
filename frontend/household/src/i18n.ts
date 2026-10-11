// English and Spanish text for the household page. Sentences that carry numbers or produce
// (fair share, read-back, consent question, pickup wording) come from the API, not from here.
import type { Language, PickupWindowPreference, TimeWindow, Weekday } from './api';

const en = {
  tagline: 'Free fresh produce for your household.',
  switchLanguage: 'Español',
  switchLanguageLabel: 'Cambiar a español',
  step: (n: number) => `Step ${n} of 3`,
  stepNames: ['Your household', 'Your food banks', 'Your pickup'] as string[],
  noPersonalInfo: 'No name, address, or income needed.',

  aboutTitle: 'About your household',
  aboutIntro: 'Tell us what works for you.',
  sizeLegend: 'How many people live in your household?',
  fewer: 'One fewer person',
  more: 'One more person',
  sizeEmpty: 'Choose a number',
  fairShareLoading: 'Getting your fair share…',
  fairShareError: "We couldn't load your fair share right now.",
  placeholderTable: 'This amount is an example for now.',
  daysLegend: 'Which days can you pick up?',
  days: { weekdays: 'Weekdays', weekends: 'Weekends', any: 'Any day' },
  timeLegend: 'What time can you pick up?',
  times: { morning: 'Morning (before noon)', afternoon: 'Afternoon (noon to 6 pm)', evening: 'Evening (after 6 pm)', any: 'Any time' },
  fridgeLegend: 'Is your fridge space limited?',
  yes: 'Yes',
  no: 'No',
  neighborhoodLabel: 'Your neighborhood or town',
  neighborhoodHint: 'Not your street address. For example: Watsonville.',
  cantEatLabel: "Anything your household can't eat?",
  cantEatHint: 'Separate with commas. Leave blank if nothing.',
  snapLegend: 'Do you receive SNAP/CalFresh? (optional)',
  snapHint: 'Your answer never changes your fair share.',
  preferNot: 'Prefer not to say',
  languageLegend: 'Which language do you prefer?',
  emailLabel: 'Email for pickup updates (optional)',
  emailHint: 'Only used to email you about pickups. Deleted after 7 days.',
  emailInvalid: 'Enter an email address, or leave it blank.',
  reviewButton: 'Review my answers',
  required: 'Please answer this question.',
  fixErrors: 'Please answer the questions marked below.',
  haveCode: 'Already have a code?',
  codeLabel: 'Your code',
  codeButton: 'See my pickup',

  reviewTitle: 'Check your answers',
  reviewIntro: 'Nothing is saved until you say yes.',
  yourAnswers: 'Your answers',
  heard: 'What HarvestNet understood',
  checking: 'Checking your answers…',
  missingTitle: 'HarvestNet still needs:',
  editAnswers: 'Change my answers',
  consentTitle: 'Can we save your answers?',
  consentFallback:
    'We keep your answers with a short code, never your name or address, and delete them after 7 days. Your SNAP/CalFresh answer is optional and never changes your share.',
  consentYes: 'Yes, save my answers',
  consentNo: "No, don't save",
  saving: 'Saving…',
  notSet: 'Not given',
  none: 'Nothing',
  people: (n: number) => (n === 1 ? '1 person' : `${n} people`),
  labels: {
    size: 'Household', days: 'Pickup days', time: 'Pickup time', fridge: 'Limited fridge space',
    neighborhood: 'Neighborhood', cantEat: "Can't eat", snap: 'SNAP/CalFresh', language: 'Language', email: 'Email for pickups',
  },

  notSavedTitle: 'Nothing was saved',
  notSavedBody: 'Your answers were not saved. You can close this page, or go back and change your answers.',
  startOver: 'Start over',

  codeIntro: 'Your code',
  codeKeep: 'Show this code at pickup. Keep it somewhere safe.',
  expires: (date: string) => `Your answers are deleted on ${date}.`,
  foodBanksTitle: 'Choose your food banks',
  foodBanksIntro: 'Pick one or more food banks you can get to. You collect your produce there.',
  loadingFoodBanks: 'Finding food banks near you…',
  noFoodBanks: 'No food banks were found near you yet.',
  pickupHours: 'Pickup hours',
  fitsYes: 'Fits your pickup times',
  fitsNo: "Doesn't fit your pickup times",
  committedHere: 'Produce confirmed for this food bank',
  nothingCommitted: 'Nothing confirmed here yet.',
  chooseError: 'Choose at least one food bank.',
  continue: 'Continue',
  badges: { keep_cold: 'Keep cold', use_within_2_days: 'Use within 2 days' } as Record<string, string>,

  pickupTitle: 'Your pickup',
  balance: (received: number, share: number) => `This week: ${received} of ${share} lb received`,
  readyTitle: 'Ready for pickup',
  waiting: "You're on the list. When produce is ready at a food bank you chose, it will show here.",
  waitingEmails: "You're on the list. We'll email you when produce is ready at a food bank you chose.",
  pickupLinkUnavailable: 'This pickup is no longer available here. Check for updates or use your code to see your current pickup.',
  useAnotherCode: 'Use another code',
  total: (lb: number) => `Total: ${lb} lb`,
  cantMakeIt: "Can't make it",
  confirmRelease: 'Give this pickup to another family?',
  confirmReleaseYes: "Yes, I can't make it",
  keepPickup: 'Keep my pickup',
  releasing: 'Sending…',
  released: 'Given to another family',
  wash: 'Please wash produce before eating.',
  marketTip: 'Tip',
  copyCode: 'Copy code',
  copied: 'Code copied.',
  copyFailed: (code: string) => `Your code is ${code}.`,
  refresh: 'Check for updates',
  loadingPickup: 'Loading your pickup…',
  back: 'Back',

  exampleTitle: 'Example data',
  exampleBody:
    "HarvestNet's test server sent made-up example answers. They don't reflect what you entered. Nothing shown is a real food bank, pickup, or code.",
  exampleReadBack: 'Example reply: it may not match your answers.',
  errorNetwork: "We couldn't reach HarvestNet. Check your connection and try again.",
  errorTimeout: 'HarvestNet is taking too long to answer. Please try again.',
  errorBusy: 'HarvestNet is busy right now. Please try again in a moment.',
  errorNotFound: "We couldn't find that. Check your code and try again.",
  errorBadInput: 'HarvestNet could not accept these answers.',
  errorConflict: 'This changed while you were looking. Please refresh and try again.',
  errorOther: 'Something went wrong. Please try again.',
  tryAgain: 'Try again',
  footer: 'HarvestNet · Fresh produce, shared fairly.',
};

export type Strings = typeof en;

const es: Strings = {
  // Spanish uses "usted" and "porción", like the voice line and the API's sentences.
  tagline: 'Frutas y verduras frescas gratis para su hogar.',
  switchLanguage: 'English',
  switchLanguageLabel: 'Switch to English',
  step: (n: number) => `Paso ${n} de 3`,
  stepNames: ['Su hogar', 'Sus bancos de alimentos', 'Su recogida'] as string[],
  noPersonalInfo: 'No necesitamos su nombre, dirección ni ingresos.',

  aboutTitle: 'Sobre su hogar',
  aboutIntro: 'Díganos qué le funciona.',
  sizeLegend: '¿Cuántas personas viven en su hogar?',
  fewer: 'Una persona menos',
  more: 'Una persona más',
  sizeEmpty: 'Elija un número',
  fairShareLoading: 'Buscando su porción…',
  fairShareError: 'No pudimos cargar su porción en este momento.',
  placeholderTable: 'Esta cantidad es un ejemplo por ahora.',
  daysLegend: '¿Qué días puede recoger?',
  days: { weekdays: 'Entre semana', weekends: 'Fines de semana', any: 'Cualquier día' },
  timeLegend: '¿A qué hora puede recoger?',
  times: { morning: 'Mañana (antes del mediodía)', afternoon: 'Tarde (del mediodía a las 6 p. m.)', evening: 'Noche (después de las 6 p. m.)', any: 'Cualquier hora' },
  fridgeLegend: '¿Tiene poco espacio en el refrigerador?',
  yes: 'Sí',
  no: 'No',
  neighborhoodLabel: 'Su vecindario o ciudad',
  neighborhoodHint: 'No su dirección. Por ejemplo: Watsonville.',
  cantEatLabel: '¿Hay algo que su hogar no pueda comer?',
  cantEatHint: 'Sepárelo con comas. Déjelo en blanco si no hay nada.',
  snapLegend: '¿Recibe SNAP/CalFresh? (opcional)',
  snapHint: 'Su respuesta nunca cambia su porción.',
  preferNot: 'Prefiero no decirlo',
  languageLegend: '¿Qué idioma prefiere?',
  emailLabel: 'Correo electrónico para avisos de recogida (opcional)',
  emailHint: 'Solo para avisarle por correo de sus recogidas. Se borra después de 7 días.',
  emailInvalid: 'Escriba un correo electrónico, o déjelo en blanco.',
  reviewButton: 'Revisar mis respuestas',
  required: 'Por favor responda esta pregunta.',
  fixErrors: 'Por favor responda las preguntas marcadas abajo.',
  haveCode: '¿Ya tiene un código?',
  codeLabel: 'Su código',
  codeButton: 'Ver mi recogida',

  reviewTitle: 'Revise sus respuestas',
  reviewIntro: 'No se guarda nada hasta que diga que sí.',
  yourAnswers: 'Sus respuestas',
  heard: 'Lo que entendió HarvestNet',
  checking: 'Revisando sus respuestas…',
  missingTitle: 'HarvestNet todavía necesita:',
  editAnswers: 'Cambiar mis respuestas',
  consentTitle: '¿Podemos guardar sus respuestas?',
  consentFallback:
    'Guardamos sus respuestas con un código corto, nunca con su nombre ni su dirección, y las borramos después de 7 días. Su respuesta sobre SNAP/CalFresh es opcional y nunca cambia su porción.',
  consentYes: 'Sí, guardar mis respuestas',
  consentNo: 'No, no guardar',
  saving: 'Guardando…',
  notSet: 'Sin respuesta',
  none: 'Nada',
  people: (n: number) => (n === 1 ? '1 persona' : `${n} personas`),
  labels: {
    size: 'Hogar', days: 'Días de recogida', time: 'Hora de recogida', fridge: 'Poco espacio en el refrigerador',
    neighborhood: 'Vecindario', cantEat: 'No pueden comer', snap: 'SNAP/CalFresh', language: 'Idioma', email: 'Correo para recogidas',
  },

  notSavedTitle: 'No se guardó nada',
  notSavedBody: 'Sus respuestas no se guardaron. Puede cerrar esta página, o volver y cambiar sus respuestas.',
  startOver: 'Empezar de nuevo',

  codeIntro: 'Su código',
  codeKeep: 'Muestre este código al recoger. Guárdelo en un lugar seguro.',
  expires: (date: string) => `Sus respuestas se borran el ${date}.`,
  foodBanksTitle: 'Elija sus bancos de alimentos',
  foodBanksIntro: 'Elija uno o más bancos de alimentos a los que pueda llegar. Ahí recoge sus frutas y verduras.',
  loadingFoodBanks: 'Buscando bancos de alimentos cerca de usted…',
  noFoodBanks: 'Todavía no encontramos bancos de alimentos cerca de usted.',
  pickupHours: 'Horario de recogida',
  fitsYes: 'Coincide con sus horarios',
  fitsNo: 'No coincide con sus horarios',
  committedHere: 'Frutas y verduras confirmadas para este banco',
  nothingCommitted: 'Todavía no hay nada confirmado aquí.',
  chooseError: 'Elija al menos un banco de alimentos.',
  continue: 'Continuar',
  badges: { keep_cold: 'Mantener en frío', use_within_2_days: 'Usar en 2 días' } as Record<string, string>,

  pickupTitle: 'Su recogida',
  balance: (received: number, share: number) => `Esta semana: ${received} de ${share} lb recibidas`,
  readyTitle: 'Ya puede recoger',
  waiting: 'Está en la lista. Cuando haya frutas y verduras listas en un banco que eligió, aparecerán aquí.',
  waitingEmails: 'Está en la lista. Le enviaremos un correo cuando haya frutas y verduras listas en un banco de alimentos que eligió.',
  pickupLinkUnavailable: 'Esta recogida ya no está disponible aquí. Busque novedades o use su código para ver su recogida actual.',
  useAnotherCode: 'Usar otro código',
  total: (lb: number) => `Total: ${lb} lb`,
  cantMakeIt: 'No puedo ir',
  confirmRelease: '¿Darle esta recogida a otra familia?',
  confirmReleaseYes: 'Sí, no puedo ir',
  keepPickup: 'Conservar mi recogida',
  releasing: 'Enviando…',
  released: 'Cedida a otra familia',
  wash: 'Por favor lave los productos antes de comerlos.',
  marketTip: 'Consejo',
  copyCode: 'Copiar código',
  copied: 'Código copiado.',
  copyFailed: (code: string) => `Su código es ${code}.`,
  refresh: 'Buscar novedades',
  loadingPickup: 'Cargando su recogida…',
  back: 'Atrás',

  exampleTitle: 'Datos de ejemplo',
  exampleBody:
    'El servidor de prueba de HarvestNet envió respuestas de ejemplo inventadas. No reflejan lo que usted escribió. Nada de lo que se muestra es un banco de alimentos, una recogida o un código reales.',
  exampleReadBack: 'Respuesta de ejemplo: puede no coincidir con sus respuestas.',
  errorNetwork: 'No pudimos conectar con HarvestNet. Revise su conexión e inténtelo de nuevo.',
  errorTimeout: 'HarvestNet está tardando demasiado. Por favor inténtelo de nuevo.',
  errorBusy: 'HarvestNet está ocupado. Por favor inténtelo de nuevo en un momento.',
  errorNotFound: 'No encontramos eso. Revise su código e inténtelo de nuevo.',
  errorBadInput: 'HarvestNet no pudo aceptar estas respuestas.',
  errorConflict: 'Esto cambió mientras lo veía. Actualice la página e inténtelo de nuevo.',
  errorOther: 'Algo salió mal. Por favor inténtelo de nuevo.',
  tryAgain: 'Intentar de nuevo',
  footer: 'HarvestNet · Frutas y verduras frescas, repartidas con justicia.',
};

export const STRINGS: Record<Language, Strings> = { en, es };

export type DaysChoice = 'weekdays' | 'weekends' | 'any';
export type TimeChoice = 'morning' | 'afternoon' | 'evening' | 'any';

const DAYS: Record<DaysChoice, Weekday[]> = {
  weekdays: ['mon', 'tue', 'wed', 'thu', 'fri'],
  weekends: ['sat', 'sun'],
  any: ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'],
};

const TIMES: Record<TimeChoice, { start: string | null; end: string | null }> = {
  morning: { start: null, end: '12:00' },
  afternoon: { start: '12:00', end: '18:00' },
  evening: { start: '18:00', end: null },
  any: { start: null, end: null },
};

/** The household's day and time choice, in the contract's weekly window shape. */
export function pickupWindow(days: DaysChoice, time: TimeChoice): PickupWindowPreference {
  return { days: [...DAYS[days]], ...TIMES[time] };
}

const LOCALES: Record<Language, string> = { en: 'en-US', es: 'es-US' };

// The API's times carry the food bank's own UTC offset. Show that wall-clock time as written,
// whatever time zone the phone is in.
function wallClock(iso: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(iso);
  if (!m) return null;
  return new Date(Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]));
}

export function formatDay(iso: string, lang: Language): string {
  const d = wallClock(iso);
  if (!d) return iso;
  return new Intl.DateTimeFormat(LOCALES[lang], { weekday: 'long', month: 'long', day: 'numeric', timeZone: 'UTC' }).format(d);
}

export function formatWindow(w: TimeWindow, lang: Language): string {
  const start = wallClock(w.start);
  const end = wallClock(w.end);
  if (!start || !end) return `${w.start} – ${w.end}`;
  const time = new Intl.DateTimeFormat(LOCALES[lang], { hour: 'numeric', minute: '2-digit', timeZone: 'UTC' });
  return `${formatDay(w.start, lang)}, ${time.format(start)} – ${time.format(end)}`;
}

export function badgeLabel(badge: string, t: Strings): string {
  return t.badges[badge] ?? badge.replace(/_/g, ' ');
}
