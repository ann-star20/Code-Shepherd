export function parseDocId(docId: string): { prefix: string; urlPart: string; hash: string } {
  const firstUnderscore = docId.indexOf("_");
  const lastUnderscore = docId.lastIndexOf("_");
  const prefix = docId.slice(0, firstUnderscore);
  const urlPart = docId.slice(firstUnderscore + 1, lastUnderscore);
  const hash = docId.slice(lastUnderscore + 1);
  return { prefix, urlPart, hash };
}
