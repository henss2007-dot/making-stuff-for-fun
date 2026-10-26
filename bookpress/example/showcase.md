---
title: The BookPress Showcase
subtitle: Every Feature on a Few Pages
author: Avery Lane
year: 2026
publisher: Driftwood Press
theme: classic
figure_numbers: true
opener_caps: 3
toc_depth: 2
the_end: true
also_by: The Lamp at Varrow Point\nSalt and Smoke
---

# Text and Emphasis
@subtitle In which the ordinary paragraph is examined
@epigraph Style is the dress of thoughts. -- Lord Chesterfield

Every paragraph is justified, hyphenated and set in a real serif. The first paragraph of a chapter gets a drop cap and, if you ask for it, a few words in small capitals. Emphasis works like Markdown: *italic*, **bold**, ***both***, __underlined__, ~~struck out~~, ^^small caps^^, superscript^2^ and subscript,,x,,, plus `typewriter` text and {red}coloured words{/}.

Quotes and dashes are converted automatically: "like this," she said -- and that's all. An ellipsis... needs three dots. A footnote looks like this[^Footnotes are collected at the end of the chapter, or in a Notes chapter at the back.] and another one here^[A second note, using the other syntax.].

## Lists

Shopping for a sea voyage:

- Hard tack and salt pork
- Fresh water in oak casks
- A good lantern, with spare wicks
  and a tin of oil

The three rules of the lighthouse:

1. Count the boats every morning.
2. Write everything down.
3. Never leave the light.

## Tables

| Year | Keeper        | Wrecks |
|:-----|:--------------|-------:|
| 1911 | T. Marrow     | 3      |
| 1954 | E. Quill      | 1      |
| 2015 | M. Quill      | 0      |

## Boxes and letters

::: box A note on the tides
The spring tides at Varrow Point run nearly two metres higher than the neaps, and the cove below the light is cut off for three hours either side of high water.

Check the tables before you walk down.
:::

::: note
A shaded note without a title. Good for asides, warnings and recipes.
:::

::: letter
My dear Teodor,

The Board has written again. I have told them what I told you.

Yours, M.
:::

::: right
Varrow Point, 3rd March
:::

# Pictures
@subtitle Captions, sizes, wrapping and plates

A picture on its own line gets a numbered caption when `figure_numbers` is on.

![The lighthouse at night.](images/lighthouse.png){width=70%}

![Text wraps around a small picture when you ask for it.](images/lighthouse.png){width=40% wrap=right}
Text can wrap around a smaller picture. The next paragraph flows beside it and continues underneath once it has passed the bottom edge of the image, which is handy for portraits, maps and little diagrams that would waste a whole line on their own. Mara had a drawer full of such things: tide tables torn from almanacs, a sketch of the cove, a photograph of her nan on the gallery with her hair blown flat.

Two pictures can sit side by side on one line:

![Morning](images/lighthouse.png) ![Evening](images/lighthouse.png){border}

And a plate takes a whole page:

![A full-page plate.](images/lighthouse.png){page}

#* Poetry and Verse

| The sea does not reward
|     those who are too anxious,
| too greedy,
|     or too impatient.

-> Centered lines <-
-> for sign-offs and the like

* * *

@pagebreak

This paragraph starts a new page because of a page break directive.
