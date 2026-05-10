export function buildScryfallBackUrl(cardBackId: string): string {
  const seg1 = cardBackId.slice(0, 2)
  const seg2 = cardBackId.slice(2, 4)
  return `https://c2.scryfall.com/file/scryfall-card-backs/large/${seg1}/${seg2}/${cardBackId}.jpg`
}
