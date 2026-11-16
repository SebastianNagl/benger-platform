/**
 * /publications page content: related work, similar projects and research
 * groups, each linking to its canonical page (DOI or arXiv page, project or
 * group website).
 *
 * Our own publications are not listed here: the page renders the
 * publication entries of `landing.news.items` from the locale catalogs, the
 * same list the landing page shows, so the two cannot drift apart.
 *
 * Titles, authors, venues and names are proper names and stay in their
 * original form. The one-line note under each entry is translated and lives
 * in the catalogs under `publicationsNetwork.entries.<id>`; a catalog test
 * checks that every id here has a note in every locale and that no note is
 * left without an entry. To add an entry: append it below, add its note to
 * de, en and fr, and only list work whose title, authors and year you
 * checked at the link you give.
 */

/** Jurisdiction label key: `publicationsNetwork.jurisdictions.<code>`. */
export type Jurisdiction =
  'ch' | 'cn' | 'de' | 'eu' | 'in' | 'intl' | 'kr' | 'us'

export interface RelatedPublication {
  id: string
  title: string
  authors: string
  venue: string
  year: number
  url: string
  jurisdiction: Jurisdiction
  /**
   * Languages of the data as ISO 639-1 codes (rendered upper case). Left out
   * when there are too many to list; the note then names them.
   */
  languages?: string[]
}

export interface NetworkLink {
  id: string
  name: string
  /** Institution or host, as it names itself; left out when it is the name. */
  institution?: string
  url: string
}

/** Legal benchmarks for other jurisdictions and languages, newest first. */
export const RELATED_PUBLICATIONS: RelatedPublication[] = [
  {
    id: 'lexam',
    title: 'LEXam: Benchmarking Legal Reasoning on 340 Law Exams',
    authors: 'Yu Fan, Jingwei Ni, Jakob Merane et al.',
    venue: 'ICLR 2026',
    year: 2025,
    url: 'https://arxiv.org/abs/2505.12864',
    jurisdiction: 'ch',
    languages: ['de', 'en'],
  },
  {
    id: 'lawbench',
    title: 'LawBench: Benchmarking Legal Knowledge of Large Language Models',
    authors: 'Zhiwei Fei, Xiaoyu Shen, Dawei Zhu et al.',
    venue: 'EMNLP 2024',
    year: 2024,
    url: 'https://doi.org/10.18653/v1/2024.emnlp-main.452',
    jurisdiction: 'cn',
    languages: ['zh'],
  },
  {
    id: 'iltur',
    title:
      'IL-TUR: Benchmark for Indian Legal Text Understanding and Reasoning',
    authors: 'Abhinav Joshi, Shounak Paul, Akshat Sharma et al.',
    venue: 'ACL 2024',
    year: 2024,
    url: 'https://doi.org/10.18653/v1/2024.acl-long.618',
    jurisdiction: 'in',
  },
  {
    id: 'legalbench',
    title:
      'LegalBench: A Collaboratively Built Benchmark for Measuring Legal Reasoning in Large Language Models',
    authors: 'Neel Guha, Julian Nyarko, Daniel E. Ho et al.',
    venue: 'NeurIPS 2023 Datasets and Benchmarks',
    year: 2023,
    url: 'https://arxiv.org/abs/2308.11462',
    jurisdiction: 'us',
    languages: ['en'],
  },
  {
    id: 'lextreme',
    title:
      'LEXTREME: A Multi-Lingual and Multi-Task Benchmark for the Legal Domain',
    authors: 'Joel Niklaus, Veton Matoshi, Pooja Rani et al.',
    venue: 'Findings of EMNLP 2023',
    year: 2023,
    url: 'https://doi.org/10.18653/v1/2023.findings-emnlp.200',
    jurisdiction: 'eu',
  },
  {
    id: 'lboxopen',
    title:
      'A Multi-Task Benchmark for Korean Legal Language Understanding and Judgement Prediction',
    authors: 'Wonseok Hwang, Dongjun Lee, Kyoungyeon Cho et al.',
    venue: 'NeurIPS 2022 Datasets and Benchmarks',
    year: 2022,
    url: 'https://arxiv.org/abs/2206.05224',
    jurisdiction: 'kr',
    languages: ['ko'],
  },
  {
    id: 'lexglue',
    title:
      'LexGLUE: A Benchmark Dataset for Legal Language Understanding in English',
    authors: 'Ilias Chalkidis, Abhik Jana, Dirk Hartung et al.',
    venue: 'ACL 2022',
    year: 2022,
    url: 'https://doi.org/10.18653/v1/2022.acl-long.297',
    jurisdiction: 'intl',
    languages: ['en'],
  },
  {
    id: 'fairlex',
    title:
      'FairLex: A Multilingual Benchmark for Evaluating Fairness in Legal Text Processing',
    authors: 'Ilias Chalkidis, Tommaso Pasini, Sheng Zhang et al.',
    venue: 'ACL 2022',
    year: 2022,
    url: 'https://doi.org/10.18653/v1/2022.acl-long.301',
    jurisdiction: 'intl',
    languages: ['en', 'de', 'fr', 'it', 'zh'],
  },
  {
    id: 'swissjudgment',
    title:
      'Swiss-Judgment-Prediction: A Multilingual Legal Judgment Prediction Benchmark',
    authors: 'Joel Niklaus, Ilias Chalkidis, Matthias Stürmer',
    venue: 'NLLP Workshop 2021',
    year: 2021,
    url: 'https://doi.org/10.18653/v1/2021.nllp-1.3',
    jurisdiction: 'ch',
    languages: ['de', 'fr', 'it'],
  },
  {
    id: 'gerdalir',
    title: 'GerDaLIR: A German Dataset for Legal Information Retrieval',
    authors: 'Marco Wrzalik, Dirk Krechel',
    venue: 'NLLP Workshop 2021',
    year: 2021,
    url: 'https://doi.org/10.18653/v1/2021.nllp-1.13',
    jurisdiction: 'de',
    languages: ['de'],
  },
  {
    id: 'casehold',
    title:
      'When Does Pretraining Help? Assessing Self-Supervised Learning for Law and the CaseHOLD Dataset',
    authors: 'Lucia Zheng, Neel Guha, Brandon R. Anderson et al.',
    venue: 'ICAIL 2021',
    year: 2021,
    url: 'https://doi.org/10.1145/3462757.3466088',
    jurisdiction: 'us',
    languages: ['en'],
  },
]

/** Benchmarks, leaderboards and open infrastructure close to BenGER. */
export const SIMILAR_PROJECTS: NetworkLink[] = [
  {
    id: 'legalbenchProject',
    name: 'LegalBench',
    institution: 'Stanford University (Hazy Research)',
    url: 'https://hazyresearch.stanford.edu/legalbench/',
  },
  {
    id: 'lexamProject',
    name: 'LEXam',
    institution: 'ETH Zurich, University of Zurich',
    url: 'https://lexam-benchmark.github.io/',
  },
  {
    id: 'lawbenchProject',
    name: 'LawBench',
    institution: 'OpenCompass',
    url: 'https://github.com/open-compass/LawBench',
  },
  {
    id: 'helm',
    name: 'HELM (Holistic Evaluation of Language Models)',
    institution: 'Stanford CRFM',
    url: 'https://crfm.stanford.edu/helm/',
  },
  {
    id: 'dynabench',
    name: 'Dynabench',
    url: 'https://dynabench.org/',
  },
  {
    id: 'openlegaldata',
    name: 'Open Legal Data',
    url: 'https://de.openlegaldata.io/',
  },
  {
    id: 'nllp',
    name: 'Natural Legal Language Processing (NLLP)',
    url: 'https://nllpw.org/',
  },
]

/** Our research group first, then related groups. */
export const OUR_GROUP: NetworkLink = {
  id: 'tumLegalTech',
  name: 'TUM Legal Tech Group',
  institution: 'Technical University of Munich',
  url: 'https://tumlegaltech.de/',
}

export const RELATED_GROUPS: NetworkLink[] = [
  {
    id: 'reglab',
    name: 'RegLab (Regulation, Evaluation, and Governance Lab)',
    institution: 'Stanford University',
    url: 'https://reglab.stanford.edu/',
  },
  {
    id: 'hazyresearch',
    name: 'Hazy Research',
    institution: 'Stanford University',
    url: 'https://hazyresearch.stanford.edu/',
  },
  {
    id: 'ethLawEcon',
    name: 'Center for Law & Economics',
    institution: 'ETH Zurich',
    url: 'https://lawecon.ethz.ch/',
  },
]

/** Every external entry, for the catalog completeness test. */
export const ALL_NETWORK_ENTRY_IDS: string[] = [
  ...RELATED_PUBLICATIONS.map((p) => p.id),
  ...SIMILAR_PROJECTS.map((p) => p.id),
  OUR_GROUP.id,
  ...RELATED_GROUPS.map((g) => g.id),
]

/**
 * Canonical paper pages for our own publications, keyed by the `url` of
 * their `landing.news.items` entry (the announcement article). Entries
 * without a paper (the poster, news) have none.
 */
export const OUR_PAPER_LINKS: Record<string, string> = {
  'https://legalplusplus.net/articles/sok-grading-legal-answers':
    'https://arxiv.org/abs/2610.19992',
  'https://legalplusplus.net/articles/benchmark-release':
    'https://arxiv.org/abs/2605.28183',
  'https://legalplusplus.net/articles/platform-release':
    'https://arxiv.org/abs/2604.13583',
}
