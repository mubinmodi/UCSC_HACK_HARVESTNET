// All the words on the landing page, in English and Spanish.
// No invented numbers (ADR 0002): the only figures on the page come from the results API and are labeled synthetic.

export type Language = 'en' | 'es';

export interface Step { title: string; body: string }
export interface Item { title: string; body: string }

export interface Strings {
  skip: string;
  nav: { problem: string; how: string; features: string; who: string; results: string };
  navLabel: string;
  login: string;
  switchLanguage: string;
  switchLanguageLabel: string;
  heroPill: string;
  heroTitle: string;
  heroLead: string;
  ctaHousehold: string;
  ctaStaff: string;
  ctaResults: string;
  heroNote: string;
  problemTitle: string;
  problemLead: string;
  problems: Item[];
  howTitle: string;
  howLead: string;
  steps: Step[];
  coolerTitle: string;
  coolerBody: string;
  featuresTitle: string;
  featuresLead: string;
  features: Item[];
  whoTitle: string;
  who: { title: string; body: string; cta: string; href: string }[];
  resultsTitle: string;
  resultsBody: string;
  resultsLink: string;
  resultsPanelTitle: (scenario: string) => string;
  resultsPanelLead: string;
  resultsFcfs: string;
  resultsRules: string;
  resultsHouseholds: string;
  resultsExample: string;
  resultsRunMode: (mode: string) => string;
  sponsorsTitle: string;
  sponsors: Item[];
  footerTeam: string;
  footerRepo: string;
  footerPhoto: (title: string) => string;
  footerHonest: string;
  loginTitle: string;
  loginLead: string;
  loginOptions: { title: string; body: string; href: string }[];
  loginClose: string;
}

const en: Strings = {
  skip: 'Skip to content',
  nav: { problem: 'The problem', how: 'How it works', features: 'Features', who: 'Who it is for', results: 'Results' },
  navLabel: 'Sections',
  login: 'Log in',
  switchLanguage: 'Español',
  switchLanguageLabel: 'Cambiar a español',
  heroPill: 'Hackathon project · all data is synthetic',
  heroTitle: 'Fresh food for families, not the trash.',
  heroLead:
    'Every food bank and donor gets its own AI agent. They negotiate how surplus produce is shared, so fresh food reaches families instead of the trash, with no central decider.',
  ctaHousehold: 'Ask for produce',
  ctaStaff: 'Donors and food banks',
  ctaResults: 'See results',
  heroNote: 'Households need no account, name or address.',
  problemTitle: 'Good produce is wasted while families nearby go without',
  problemLead: 'Surplus fruit and vegetables spoil within days. Moving them fairly and fast is the hard part.',
  problems: [
    {
      title: 'Surplus spoils',
      body: 'Farms, grocers and farmers markets end up with good produce they cannot sell. An over-ordered pallet, the last of a market day. It will not last the week.',
    },
    {
      title: 'Nearby families need it',
      body: 'Low-income households would use it. But a parent who works until 6 pm cannot collect lettuce at 2 pm, and a small donor has no truck.',
    },
    {
      title: 'Who decides is the hard part',
      body: 'A food bank in a low-access area can get far less than one near the donors. A central decider becomes one point of failure and one point of blame. HarvestNet has none.',
    },
  ],
  howTitle: 'How it works',
  howLead: 'Every Organization keeps its own keys. The food still moves.',
  steps: [
    {
      title: 'A donor reports surplus',
      body: 'A farmers market, grocer or farm says what it has, when it must leave, and whether it can drop it off.',
    },
    {
      title: 'Each Organization has a Negotiator',
      body: 'Donors and food banks each get an AI agent. An advocate speaks for the households furthest below their fair share. It can propose, but it cannot vote. Numbers come from calculators (Specialists), never from the AI.',
    },
    {
      title: 'They negotiate, with reasons',
      body: 'The agents split the lot item by item. Every change is a new version with a reason. The system can agree, keep a disagreement, or ask a human.',
    },
    {
      title: 'People approve the exact version',
      body: 'Each manager approves one specific version by email. If anyone changes the terms, old approvals stop counting. Nothing is committed automatically.',
    },
  ],
  coolerTitle: 'When a cooler fails, the plan changes',
  coolerBody:
    'If a food bank’s walk-in cooler fails, its agent checks which produce must stay cold, searches the Directory for food banks with cold space, and writes a reason card for each choice. The new plan is a new version, so the managers approve again.',
  featuresTitle: 'What it does',
  featuresLead: 'Built for the Cisco “When AI Agents Disagree” challenge, Level 3.',
  features: [
    {
      title: 'A household page in English and Spanish',
      body: 'Ask for produce from a phone. No name, no address, no income. Pick up with a short code.',
    },
    {
      title: 'A fair share, set like SNAP',
      body: 'A weekly produce amount that grows with household size, from a published table. It is the yardstick for fairness, not a ration.',
    },
    {
      title: 'Agents negotiate, with reasons',
      body: 'Each food bank and donor has its own agent. Offers are checked against real limits, and disagreements stay visible.',
    },
    {
      title: 'Human approvals by email',
      body: 'Managers approve the exact version of a plan. Change the terms and the old approvals stop counting.',
    },
    {
      title: 'Cooler-failure recovery',
      body: 'Agents find food banks with cold space by capability and explain why each was chosen or passed over.',
    },
    {
      title: 'Honest results',
      body: 'We compare against first-come-first-served on the same inputs, and we show where negotiation does worse too.',
    },
  ],
  whoTitle: 'Who it is for',
  who: [
    {
      title: 'Households',
      body: 'Ask for fresh produce and choose the food banks you will collect from. No app, no account, no name.',
      cta: 'Open the household page',
      href: '/household/',
    },
    {
      title: 'Donors',
      body: 'Farms, packers, grocers and farmers markets report surplus and say whether they can drop it off.',
      cta: 'Open the donor page',
      href: '/donor-dashboard/',
    },
    {
      title: 'Food banks',
      body: 'Set storage and pickup hours, see disagreements, and approve what comes in.',
      cta: 'Open the food bank dashboard',
      href: '/donor-dashboard/',
    },
  ],
  resultsTitle: 'Honest results',
  resultsBody:
    'Every number in this demo is synthetic. We compare negotiation with first-come-first-served on the same made-up scenarios, and we say when a result is not measured, partial, or not run. We never claim households fed or pounds saved.',
  resultsLink: 'Open the results strip',
  resultsPanelTitle: scenario => `From the results API · scenario “${scenario}”`,
  resultsPanelLead: 'Synthetic scenario. Households counted by pickup confirmations.',
  resultsFcfs: 'First-come-first-served',
  resultsRules: 'Rules-based negotiators',
  resultsHouseholds: 'households reached',
  resultsExample: 'Example data, not a measured result.',
  resultsRunMode: mode => `Run mode: ${mode}`,
  sponsorsTitle: 'Built with',
  sponsors: [
    { title: 'Cisco AGNTCY', body: 'Agent messages and Directory discovery' },
    { title: 'n8n', body: 'Approval and pickup emails' },
    { title: 'Amazon SES and AWS', body: 'Email delivery and hosting' },
    { title: 'ElevenLabs', body: 'A voice line, in English and Spanish (being set up)' },
    { title: 'Claude', body: 'Negotiators, advocate and front desk' },
    { title: 'Beeceptor', body: 'Mock inventory, storage and cooler status' },
  ],
  footerTeam: 'Built by the HarvestNet team for the UCSC AI Hackathon, Cisco Cloud Track.',
  footerRepo: 'Source code on GitHub',
  footerPhoto: title => `Photo: “${title}”`,
  footerHonest: 'All data on this site is synthetic. Nothing here is a real offer of food.',
  loginTitle: 'Log in',
  loginLead: 'HarvestNet has no user accounts. Households need no account at all. Staff sign in with their organization’s access token.',
  loginOptions: [
    { title: 'I’m a household', body: 'No account needed. Ask for produce or check a pickup.', href: '/household/' },
    { title: 'Donor or food bank staff', body: 'Sign in on the next page with your organization’s token.', href: '/donor-dashboard/' },
    { title: 'See results', body: 'Compare negotiation with first-come-first-served (synthetic data).', href: '/results-strip/' },
  ],
  loginClose: 'Close',
};

const es: Strings = {
  skip: 'Saltar al contenido',
  nav: { problem: 'El problema', how: 'Cómo funciona', features: 'Funciones', who: 'Para quién es', results: 'Resultados' },
  navLabel: 'Secciones',
  login: 'Iniciar sesión',
  switchLanguage: 'English',
  switchLanguageLabel: 'Switch to English',
  heroPill: 'Proyecto de hackatón · todos los datos son sintéticos',
  heroTitle: 'Comida fresca para las familias, no para la basura.',
  heroLead:
    'Cada banco de alimentos y cada donante tiene su propio agente de IA. Negocian cómo se reparte el producto sobrante, para que la comida fresca llegue a las familias y no a la basura, sin un decisor central.',
  ctaHousehold: 'Pedir productos',
  ctaStaff: 'Donantes y bancos de alimentos',
  ctaResults: 'Ver resultados',
  heroNote: 'Los hogares no necesitan cuenta, nombre ni dirección.',
  problemTitle: 'Se desperdicia producto bueno mientras familias cercanas pasan necesidad',
  problemLead: 'Las frutas y verduras sobrantes se echan a perder en pocos días. Repartirlas con justicia y rapidez es lo difícil.',
  problems: [
    {
      title: 'El sobrante se echa a perder',
      body: 'Granjas, tiendas y mercados agrícolas se quedan con producto bueno que no pueden vender. Una paleta pedida de más, lo último de un día de mercado. No dura la semana.',
    },
    {
      title: 'Las familias cercanas lo necesitan',
      body: 'Los hogares de bajos ingresos lo aprovecharían. Pero quien trabaja hasta las 6 pm no puede recoger lechuga a las 2 pm, y un donante pequeño no tiene camión.',
    },
    {
      title: 'Lo difícil es quién decide',
      body: 'Un banco de alimentos en una zona de poco acceso puede recibir mucho menos que uno cerca de los donantes. Un decisor central es un único punto de falla y de culpa. HarvestNet no tiene ninguno.',
    },
  ],
  howTitle: 'Cómo funciona',
  howLead: 'Cada organización conserva sus propias llaves. La comida sigue llegando.',
  steps: [
    {
      title: 'Un donante avisa de su sobrante',
      body: 'Un mercado agrícola, una tienda o una granja dice qué tiene, cuándo debe salir y si puede llevarlo.',
    },
    {
      title: 'Cada organización tiene un negociador',
      body: 'Donantes y bancos de alimentos tienen cada uno un agente de IA. Una defensora habla por los hogares más lejos de su porción justa. Puede proponer, pero no votar. Los números vienen de calculadoras (especialistas), nunca de la IA.',
    },
    {
      title: 'Negocian, con razones',
      body: 'Los agentes reparten el lote producto por producto. Cada cambio es una versión nueva con su razón. El sistema puede llegar a un acuerdo, mantener un desacuerdo o pedir ayuda a una persona.',
    },
    {
      title: 'Las personas aprueban la versión exacta',
      body: 'Cada gerente aprueba por correo una versión concreta. Si alguien cambia los términos, las aprobaciones anteriores dejan de contar. Nada se compromete automáticamente.',
    },
  ],
  coolerTitle: 'Si falla una cámara fría, el plan cambia',
  coolerBody:
    'Si falla la cámara fría de un banco de alimentos, su agente revisa qué producto debe mantenerse frío, busca en el Directorio bancos con espacio frío y escribe una tarjeta de razones para cada elección. El plan nuevo es una versión nueva, así que los gerentes vuelven a aprobar.',
  featuresTitle: 'Qué hace',
  featuresLead: 'Hecho para el reto de Cisco “When AI Agents Disagree”, nivel 3.',
  features: [
    {
      title: 'Una página para hogares en español e inglés',
      body: 'Pida productos desde el teléfono. Sin nombre, sin dirección, sin ingresos. Recoja con un código corto.',
    },
    {
      title: 'Una porción justa, como SNAP',
      body: 'Una cantidad semanal de producto que crece con el tamaño del hogar, según una tabla pública. Es la medida de justicia, no una ración.',
    },
    {
      title: 'Los agentes negocian, con razones',
      body: 'Cada banco de alimentos y cada donante tiene su agente. Las ofertas se comprueban contra límites reales y los desacuerdos se ven.',
    },
    {
      title: 'Aprobaciones humanas por correo',
      body: 'Los gerentes aprueban la versión exacta de un plan. Si cambian los términos, las aprobaciones anteriores dejan de contar.',
    },
    {
      title: 'Recuperación ante fallas de refrigeración',
      body: 'Los agentes encuentran bancos con espacio frío por su capacidad y explican por qué eligieron o descartaron cada uno.',
    },
    {
      title: 'Resultados honestos',
      body: 'Comparamos con el orden de llegada usando los mismos datos, y también mostramos dónde la negociación lo hace peor.',
    },
  ],
  whoTitle: 'Para quién es',
  who: [
    {
      title: 'Hogares',
      body: 'Pida producto fresco y elija los bancos de alimentos donde lo recogerá. Sin app, sin cuenta, sin nombre.',
      cta: 'Abrir la página para hogares',
      href: '/household/',
    },
    {
      title: 'Donantes',
      body: 'Granjas, empacadoras, tiendas y mercados agrícolas avisan de su sobrante y dicen si pueden llevarlo.',
      cta: 'Abrir la página de donantes',
      href: '/donor-dashboard/',
    },
    {
      title: 'Bancos de alimentos',
      body: 'Definen almacenamiento y horarios, ven los desacuerdos y aprueban lo que llega.',
      cta: 'Abrir el panel de bancos de alimentos',
      href: '/donor-dashboard/',
    },
  ],
  resultsTitle: 'Resultados honestos',
  resultsBody:
    'Todos los números de esta demostración son sintéticos. Comparamos la negociación con el orden de llegada en los mismos escenarios inventados, y decimos cuándo un resultado no está medido, es parcial o no se ejecutó. Nunca afirmamos hogares alimentados ni libras salvadas.',
  resultsLink: 'Abrir la tira de resultados',
  resultsPanelTitle: scenario => `De la API de resultados · escenario “${scenario}”`,
  resultsPanelLead: 'Escenario sintético. Hogares contados por confirmaciones de recogida.',
  resultsFcfs: 'Por orden de llegada',
  resultsRules: 'Negociadores con reglas',
  resultsHouseholds: 'hogares alcanzados',
  resultsExample: 'Datos de ejemplo, no un resultado medido.',
  resultsRunMode: mode => `Modo de ejecución: ${mode}`,
  sponsorsTitle: 'Hecho con',
  sponsors: [
    { title: 'Cisco AGNTCY', body: 'Mensajes entre agentes y búsqueda en el Directorio' },
    { title: 'n8n', body: 'Correos de aprobación y de recogida' },
    { title: 'Amazon SES y AWS', body: 'Envío de correo y alojamiento' },
    { title: 'ElevenLabs', body: 'Una línea de voz, en español e inglés (en preparación)' },
    { title: 'Claude', body: 'Negociadores, defensora y recepción' },
    { title: 'Beeceptor', body: 'Inventario, almacenamiento y estado de cámaras simulados' },
  ],
  footerTeam: 'Hecho por el equipo de HarvestNet para el hackatón de IA de UCSC, Cisco Cloud Track.',
  footerRepo: 'Código fuente en GitHub',
  footerPhoto: title => `Foto: “${title}”`,
  footerHonest: 'Todos los datos de este sitio son sintéticos. Nada aquí es una oferta real de comida.',
  loginTitle: 'Iniciar sesión',
  loginLead: 'HarvestNet no tiene cuentas de usuario. Los hogares no necesitan ninguna cuenta. El personal entra con el token de acceso de su organización.',
  loginOptions: [
    { title: 'Soy un hogar', body: 'No necesita cuenta. Pida productos o consulte una recogida.', href: '/household/' },
    { title: 'Personal de donante o banco de alimentos', body: 'Entre en la página siguiente con el token de su organización.', href: '/donor-dashboard/' },
    { title: 'Ver resultados', body: 'Compare la negociación con el orden de llegada (datos sintéticos).', href: '/results-strip/' },
  ],
  loginClose: 'Cerrar',
};

export const STRINGS: Record<Language, Strings> = { en, es };
