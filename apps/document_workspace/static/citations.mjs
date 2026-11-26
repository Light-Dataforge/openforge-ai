// Preserve original source numbers when older answers reference sparse citations.
export function citedSources(content, sources) {
  if (!Array.isArray(sources)) return [];
  const numbers = new Set([...String(content || '').matchAll(/\[(\d+)\]/g)].map(match => Number(match[1])));
  return sources.flatMap((source, index) => numbers.has(index + 1) ? [{source, index, number: index + 1}] : []);
}

export function answerNote(content, sources) {
  const cited = citedSources(content, sources);
  const references = cited.map(({source, number}) => `[${number}] ${source.document_name || 'Source document'} — page ${source.page}`).join('\n');
  return {
    text: String(content || '') + (references ? '\n\nSources:\n' + references : ''),
    source: cited.length === 1 ? cited[0].source : {document_id: null, page: null},
  };
}
