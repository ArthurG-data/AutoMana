// src/frontend/src/mocks/data.ts
import type { CardSummary, CardDetail } from '../features/cards/types'

function makeSpark(start: number, end: number, n = 30): number[] {
  const arr: number[] = []
  const step = (end - start) / (n - 1)
  for (let i = 0; i < n; i++) arr.push(+(start + step * i + (Math.random() - 0.5) * step * 0.8).toFixed(2))
  arr[arr.length - 1] = end
  return arr
}

export const MOCK_CARDS: CardSummary[] = [
  { id: 'ragavan-mh2',     name: 'Ragavan, Nimble Pilferer', set: 'MH2', set_name: 'Modern Horizons 2', finish: 'non-foil', rarity: 'mythic', price: 84.50, price_change_1d: 2.4,  price_change_7d: 6.1,  price_change_30d: -3.2, image_uri: null, spark: makeSpark(62, 84.5)  },
  { id: 'one-ring-ltr',    name: 'The One Ring',              set: 'LTR', set_name: 'LotR',              finish: 'non-foil', rarity: 'mythic', price: 62.10, price_change_1d: -0.8, price_change_7d: 1.4,  price_change_30d: 12.7, image_uri: null, spark: makeSpark(48, 62.1)  },
  { id: 'bowmasters-ltr',  name: 'Orcish Bowmasters',         set: 'LTR', set_name: 'LotR',              finish: 'non-foil', rarity: 'rare',   price: 41.20, price_change_1d: 1.1,  price_change_7d: -2.3, price_change_30d: 5.6,  image_uri: null, spark: makeSpark(35, 41.2)  },
  { id: 'sheoldred-dmu',   name: 'Sheoldred, the Apocalypse', set: 'DMU', set_name: 'Dominaria United',  finish: 'non-foil', rarity: 'mythic', price: 76.00, price_change_1d: 0.4,  price_change_7d: 3.8,  price_change_30d: -1.1, image_uri: null, spark: makeSpark(78, 76)    },
  { id: 'wrenn-mh1',       name: 'Wrenn and Six',             set: 'MH1', set_name: 'Modern Horizons 1', finish: 'non-foil', rarity: 'mythic', price: 51.30, price_change_1d: -1.6, price_change_7d: -4.2, price_change_30d: -8.1, image_uri: null, spark: makeSpark(60, 51.3)  },
  { id: 'fow-ema',         name: 'Force of Will',             set: 'EMA', set_name: 'Eternal Masters',   finish: 'non-foil', rarity: 'rare',   price: 88.40, price_change_1d: 0.2,  price_change_7d: 0.9,  price_change_30d: 2.1,  image_uri: null, spark: makeSpark(85, 88.4)  },
  { id: 'mox-sth',         name: 'Mox Diamond',               set: 'STH', set_name: 'Stronghold',        finish: 'non-foil', rarity: 'rare',   price: 612.0, price_change_1d: 3.2,  price_change_7d: 8.1,  price_change_30d: 14.4, image_uri: null, spark: makeSpark(520, 612)  },
  { id: 'shredder-snc',    name: 'Ledger Shredder',           set: 'SNC', set_name: 'Streets of NCI',    finish: 'non-foil', rarity: 'rare',   price: 14.80, price_change_1d: -0.4, price_change_7d: 1.2,  price_change_30d: -2.8, image_uri: null, spark: makeSpark(16, 14.8)  },
]

export const MOCK_CARD_DETAIL: Record<string, CardDetail> = {
  'ragavan-mh2': {
    ...MOCK_CARDS[0],
    mana_cost: '{R}',
    type_line: 'Legendary Creature — Monkey Pirate',
    oracle_text: "Whenever Ragavan, Nimble Pilferer deals combat damage to a player, create a Treasure token and exile the top card of that player's library. Until end of turn, you may cast that card.\nDash {R}",
    artist: 'Simon Dominic',
    price_history: makeSpark(50, 84.5, 365),
    prints: [
      { id: 'ragavan-mh2-foil',   set: 'MH2', set_name: 'Modern Horizons 2', finish: 'foil',     price: 110.0, image_uri: null },
      { id: 'ragavan-mh2-etched', set: 'MH2', set_name: 'Modern Horizons 2', finish: 'etched',   price: 95.0,  image_uri: null },
      { id: 'ragavan-mh2-retro',  set: 'MH2', set_name: 'Modern Horizons 2', finish: 'non-foil', price: 88.0,  image_uri: null },
    ],
  },
}
