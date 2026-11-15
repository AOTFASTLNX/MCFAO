# System Neutral UI

## Visual tokens

- Light: window `#F5F5F7`, content `#FFFFFF`, sidebar `#ECEDEF`, secondary
  `#F6F7F9`, text `#25262A`, muted `#62666F`, border `#E3E4E8`.
- Dark: window `#18191B`, content `#27282B`, sidebar `#222326`, secondary
  `#303136`, text `#EFEFF1`, muted `#B3B5BB`, border `#414248`.
- Semantic: success `#2F8F6C`, warning `#A96F16`, danger `#B94F4F`,
  experimental `#746CC0`; foreground/background pairs meet WCAG AA.
- Spacing: 4/8/12/16/20/24/32 px; radius 5/8/11 px; control height 30 px.
- Type: macOS system stack; mono logs use SF Mono.

## Interaction

- Accent comes from macOS `controlAccentColor`, overridable in settings.
  Light mode darkens the same hue only enough for white text contrast; status
  colors never change with the accent.
- Native focus rings, hover and disabled states on every control; dialogs close
  with Escape and return focus.
- Logs label INFO/WARN/ERROR in text as well as color.

## Layout

- Compact sidebar, sticky overlay toolbar, one content grid, 5-step Fabric flow
  and 4-step vanilla flow.
- Responsive at 1100×760, 800×640, 768 and 375; no horizontal page overflow.
