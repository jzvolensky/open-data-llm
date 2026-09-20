import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const config: Config = {
  title: 'Bratislava Open Data LLM',
  tagline: 'Retrieval-augmented answering over data.bratislava.sk',
  favicon: 'img/favicon.ico',

  future: {
    v4: true,
  },

  // Overridable at build time (see .github/workflows/docs.yml for GitHub Pages).
  url: process.env.DOCS_URL ?? 'https://example.github.io',
  baseUrl: process.env.DOCS_BASE_URL ?? '/',
  onBrokenLinks: 'warn',

  markdown: {
    mermaid: true,
  },
  themes: ['@docusaurus/theme-mermaid'],

  i18n: {
    defaultLocale: 'en',
    locales: ['en', 'sk'],
    localeConfigs: {
      en: {label: 'English', direction: 'ltr'},
      sk: {label: 'Slovenčina', direction: 'ltr'},
    },
  },

  presets: [
    [
      'classic',
      {
        docs: {
          routeBasePath: '/',
          sidebarPath: './sidebars.ts',
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],

  themeConfig: {
    colorMode: {
      respectPrefersColorScheme: true,
    },
    navbar: {
      title: 'Bratislava Open Data LLM',
      logo: {
        alt: 'Bratislava Open Data LLM',
        src: 'img/logo.svg',
      },
      items: [
        {
          type: 'docSidebar',
          sidebarId: 'docsSidebar',
          position: 'left',
          label: 'Documentation',
        },
        {
          type: 'localeDropdown',
          position: 'right',
        },
        {
          href: 'https://data.bratislava.sk',
          label: 'data.bratislava.sk',
          position: 'right',
        },
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Documentation',
          items: [
            {label: 'Architecture', to: '/architecture'},
            {label: 'Models', to: '/models'},
            {label: 'Evaluation', to: '/evaluation'},
          ],
        },
        {
          title: 'Data',
          items: [
            {label: 'OpenData Bratislava', href: 'https://data.bratislava.sk'},
          ],
        },
        {
          title: 'Author',
          items: [
            {
              label: 'Juraj Zvolenský (@jzvolensky)',
              href: 'https://github.com/jzvolensky',
            },
            {
              label: 'open-data-llm',
              href: 'https://github.com/jzvolensky/open-data-llm',
            },
          ],
        },
      ],
      copyright: `© ${new Date().getFullYear()} Juraj Zvolenský · Built with Docusaurus · Data: OpenData Bratislava (CC BY 4.0).`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
