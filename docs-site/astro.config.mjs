import { defineConfig } from "astro/config";
import { unified } from "@astrojs/markdown-remark";
import starlight from "@astrojs/starlight";

// Origin of the deployed docs. It feeds the sitemap, canonical links and og:image,
// and public/robots.txt and scripts/check-links.mjs repeat it.
const site = "https://kelvis-evalgate.vercel.app";

// Wraps a table cell that says exactly PASS or FAIL so CSS can mark it.
// Small enough to keep here instead of pulling in a plugin.
function rehypeStatusCells() {
  const visit = (node) => {
    if (
      node.type === "element" &&
      node.tagName === "td" &&
      node.children?.length === 1
    ) {
      const [child] = node.children;
      if (
        child.type === "text" &&
        (child.value === "PASS" || child.value === "FAIL")
      ) {
        node.children = [
          {
            type: "element",
            tagName: "span",
            properties: { className: ["eg-status"], dataStatus: child.value },
            children: [child],
          },
        ];
      }
    }
    node.children?.forEach(visit);
  };
  return (tree) => visit(tree);
}

export default defineConfig({
  site,
  markdown: { processor: unified({ rehypePlugins: [rehypeStatusCells] }) },
  integrations: [
    starlight({
      title: "evalgate",
      description:
        "Documentation for evalgate, a CI gate that fails a build when RAG or LLM answer quality drops below a committed baseline.",
      favicon: "/favicon.svg",
      logo: {
        light: "./src/assets/logo-light.svg",
        dark: "./src/assets/logo-dark.svg",
        alt: "",
      },
      customCss: ["./src/styles/evalgate.css"],
      head: [
        {
          tag: "meta",
          attrs: { property: "og:image", content: `${site}/og.png` },
        },
        { tag: "meta", attrs: { property: "og:image:width", content: "1200" } },
        { tag: "meta", attrs: { property: "og:image:height", content: "630" } },
        {
          tag: "meta",
          attrs: {
            property: "og:image:alt",
            content: "evalgate: a CI gate for RAG and LLM apps",
          },
        },
        {
          tag: "meta",
          attrs: { name: "twitter:card", content: "summary_large_image" },
        },
        {
          tag: "meta",
          attrs: { name: "twitter:image", content: `${site}/og.png` },
        },
      ],
      sidebar: [
        { label: "Getting started", slug: "getting-started" },
        {
          label: "Concepts",
          items: [
            { slug: "concepts/eval-set" },
            { slug: "concepts/metrics" },
            { slug: "concepts/baseline-and-tolerance" },
            { slug: "concepts/exit-codes" },
          ],
        },
        {
          label: "Guides",
          items: [
            { slug: "guides/own-app" },
            { slug: "guides/github-actions" },
            { slug: "guides/update-baseline" },
            { slug: "guides/read-a-report" },
          ],
        },
        {
          label: "Reference",
          items: [{ slug: "reference/cli" }, { slug: "reference/demo" }],
        },
        {
          label: "Project",
          items: [
            { slug: "limitations" },
            { slug: "decisions" },
            { slug: "changelog" },
          ],
        },
      ],
    }),
  ],
});
