// @ts-check
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'astro/config';
import react from '@astrojs/react';
import starlight from '@astrojs/starlight';
import starlightLlmsTxt from 'starlight-llms-txt';

// The design system lives in the report's source (ui/src/ds), outside this folder.
// It comes in only through the @ds alias, so moving the site elsewhere means changing it here.
const ds = fileURLToPath(new URL('../ui/src/ds', import.meta.url));

// The docs open in light mode, like the landing page, until the reader picks a theme.
// Starlight stores the choice under this key ('' means "auto"), so only a missing key is set.
const lightByDefault = `if (localStorage.getItem('starlight-theme') === null) localStorage.setItem('starlight-theme', 'light');`;

export default defineConfig({
  site: 'https://thehonestagent.dev',
  integrations: [
    starlight({
      title: 'honest-agent',
      // /llms.txt, /llms-full.txt and /llms-small.txt: the docs as Markdown, for coding agents and LLMs.
      plugins: [
        starlightLlmsTxt({
          projectName: 'The Honest Agent (honest-agent)',
          description:
            "honest-agent tests an AI analytics agent the way you'd test code: with questions you already know the answers to. " +
            "Every eval checks two things about the agent's answer: accuracy (is the answer right?) and provenance " +
            "(did the agent's SQL read the tables your team trusts for that question?).",
          optionalLinks: [{ label: 'GitHub', url: 'https://github.com/jlcoto/the_honest_agent' }],
        }),
      ],
      logo: { src: './public/assets/robot.png', alt: 'The Honest Agent robot' },
      favicon: '/favicon.svg',
      // Only the tokens: the design system's base.css restyles html, body and links, which is
      // right for the landing page and the report but would fight Starlight's own styles.
      customCss: [
        '@ds/tokens/fonts.css',
        '@ds/tokens/colors.css',
        '@ds/tokens/typography.css',
        '@ds/tokens/spacing.css',
        './src/styles/docs.css',
      ],
      head: [
        { tag: 'script', content: lightByDefault },
        // The landing page's share image, for links to the docs too.
        { tag: 'meta', attrs: { property: 'og:image', content: 'https://thehonestagent.dev/assets/og.png' } },
        { tag: 'meta', attrs: { property: 'og:image:width', content: '1200' } },
        { tag: 'meta', attrs: { property: 'og:image:height', content: '630' } },
        { tag: 'meta', attrs: { name: 'twitter:image', content: 'https://thehonestagent.dev/assets/og.png' } },
      ],
      social: [{ icon: 'github', label: 'GitHub', href: 'https://github.com/jlcoto/the_honest_agent' }],
      editLink: { baseUrl: 'https://github.com/jlcoto/the_honest_agent/edit/main/site/' },
      sidebar: [
        { label: 'Overview', link: '/docs/' },
        { label: 'What are evals for agentic analytics?', link: '/docs/evals-for-agentic-analytics/' },
        { label: 'Getting started', link: '/docs/getting-started/' },
        {
          label: 'Connect your agent',
          items: [
            { label: 'Overview', link: '/docs/connect/' },
            { label: 'Snowflake', link: '/docs/connect/snowflake/' },
            { label: 'MotherDuck', link: '/docs/connect/motherduck/' },
          ],
        },
        { label: 'Writing evals', link: '/docs/writing-evals/' },
        { label: 'Running evals', link: '/docs/running-evals/' },
        { label: 'Storing results', link: '/docs/storing-results/' },
        { label: 'The report', link: '/docs/report/' },
        { label: 'Setting up alerts', link: '/docs/alerts/' },
        { label: 'Troubleshooting', link: '/docs/troubleshooting/' },
        {
          label: 'Running it for a team',
          items: [
            { label: 'Overview', link: '/docs/team/' },
            { label: 'Store results in MotherDuck', link: '/docs/team/results-motherduck/' },
            { label: 'Store results in S3', link: '/docs/team/results-s3/' },
            { label: 'Host the report on Cloudflare', link: '/docs/team/report-cloudflare/' },
            { label: 'Host the report on AWS', link: '/docs/team/report-aws/' },
            { label: 'Run it in GitHub Actions', link: '/docs/team/ci/' },
            { label: 'Run it in a container', link: '/docs/team/container/' },
          ],
        },
        {
          label: 'Reference',
          items: [
            { label: 'CLI commands', link: '/docs/reference/cli/' },
            { label: 'Config keys', link: '/docs/reference/config/' },
          ],
        },
      ],
    }),
    react(),
  ],
  vite: {
    // dedupe: one React even when ui/node_modules has its own copy.
    resolve: { alias: { '@ds': ds }, dedupe: ['react', 'react-dom'] },
    server: { fs: { allow: ['..'] } },
  },
});
