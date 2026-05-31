import { Link } from '@tanstack/react-router'
import type { ArticleSummary } from '../types'
import styles from './ArticleGrid.module.css'

// Deterministic gradient placeholder cover until cover_image_url lands.
function gradientFor(seed: string): string {
  let h = 0
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) % 360
  return `linear-gradient(135deg, hsl(${h} 45% 22%), hsl(${(h + 40) % 360} 55% 12%))`
}

export function ArticleGrid({ articles }: { articles: ArticleSummary[] }) {
  if (articles.length === 0) {
    return <p className={styles.empty}>No articles published yet.</p>
  }
  return (
    <div className={styles.grid}>
      {articles.map((a) => (
        <Link key={a.article_id} to="/analysis/$slug" params={{ slug: a.slug }} className={styles.card}>
          <div
            className={styles.cover}
            style={a.cover_image_url
              ? { backgroundImage: `url(${a.cover_image_url})` }
              : { backgroundImage: gradientFor(a.slug) }}
          />
          <div className={styles.body}>
            {a.tags[0] && <span className={styles.tag}>{a.tags[0]}</span>}
            <h3 className={styles.title}>{a.title}</h3>
            <p className={styles.excerpt}>{a.excerpt}</p>
            <div className={styles.meta}>
              {a.published_at ? new Date(a.published_at).toLocaleDateString() : 'Draft'} · {a.read_minutes} min
            </div>
          </div>
        </Link>
      ))}
    </div>
  )
}
