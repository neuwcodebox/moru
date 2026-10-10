import { useTranslation } from "react-i18next";
import type { PromptSource } from "../../api";
import Modal from "../../components/Modal";

function TagLink({ name }: { name: string }) {
  return <a href={`https://safebooru.donmai.us/wiki_pages/${encodeURIComponent(name)}`}
    target="_blank" rel="noopener noreferrer">{name}</a>;
}

function TagList({ tags }: { tags: string[] }) {
  return <ul className="source-tags">
    {tags.map((name) => <li key={name}><TagLink name={name} /></li>)}
  </ul>;
}

function ReferenceResult({ source }: { source: PromptSource }) {
  const { t } = useTranslation("dialogs");
  const result = source.result;
  if (Array.isArray(result)) {
    return result.length ? <TagList tags={result} /> : <p className="hint">{t("sources.noResults")}</p>;
  }
  if ("error" in result) return <p className="hint">{t("sources.unavailable")}</p>;
  if ("name" in result) return <>
    {result.name && result.name !== source.query && <p><TagLink name={result.name} /></p>}
    {result.deprecated && <p className="hint">{t("sources.deprecated")}</p>}
    {result.description && <p className="source-description">{result.description}</p>}
    {!result.name && !result.description && <p className="hint">{t("sources.noResults")}</p>}
  </>;
  if (!result.cooccurring.length && !result.wiki_links.length)
    return <p className="hint">{t("sources.noResults")}</p>;
  return <>
    {result.cooccurring.length > 0 && <div role="group" aria-label={t("sources.cooccurring")}>
      <h4>{t("sources.cooccurring")}</h4><TagList tags={result.cooccurring} />
    </div>}
    {result.wiki_links.length > 0 && <div role="group" aria-label={t("sources.wikiLinks")}>
      <h4>{t("sources.wikiLinks")}</h4><TagList tags={result.wiki_links} />
    </div>}
  </>;
}

export default function SourcesDialog({ sources, onClose, onReturnFocus }: {
  sources: PromptSource[];
  onClose: () => void;
  onReturnFocus?: () => void;
}) {
  const { t } = useTranslation("dialogs");
  return <Modal title={t("sources.title")} onClose={onClose} className="sources-dialog" onReturnFocus={onReturnFocus}>
    {sources.length === 0 ? <p className="hint">{t("sources.empty")}</p> :
      <ol className="prompt-sources">
        {sources.map((source, index) => {
          const result = source.result;
          const canonical = !Array.isArray(result) && "name" in result ? result.name : null;
          return <li className="prompt-source" key={index}>
            <h3>{t(`sources.tools.${source.tool}`)}</h3>
            <div className="source-query">{canonical === source.query
              ? <TagLink name={canonical} /> : source.query}</div>
            <ReferenceResult source={source} />
          </li>;
        })}
      </ol>}
    <div className="modal-actions"><button onClick={onClose}>{t("common.close")}</button></div>
  </Modal>;
}
