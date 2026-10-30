#set document(title: "Measured workflow reuse", author: "Ashton Liu")
#set page(paper: "us-letter", margin: (x: 0.65in, top: 0.55in, bottom: 0.55in),
  header: context { if counter(page).get().first() > 1 {
    text(size: 7.5pt, fill: rgb("64748b"))[ASHTON LIU / MEASURED WORKFLOW REUSE]
  } },
  footer: context align(right, text(size: 7.5pt, fill: rgb("64748b"), counter(page).display("1"))))
#set text(font: "Libertinus Serif", size: 9.5pt, fill: rgb("14283f"))
#set par(justify: false, leading: 0.5em, spacing: 0.6em)
#set heading(numbering: none)
#show heading.where(level: 1): it => block(above: 0pt, below: 6pt, sticky: true,
  text(size: 22pt, weight: "bold", fill: rgb("123e59"), it.body))
#show heading.where(level: 2): it => block(above: 8pt, below: 4pt, sticky: true,
  text(size: 13pt, weight: "bold", fill: rgb("126d73"), it.body))
#show raw: set text(font: "DejaVu Sans Mono", size: 8pt)
#show link: set text(fill: rgb("0c7287"))
#show image: it => align(center, it)
#set image(width: 100%)
#set figure(gap: 4pt)
#show figure.caption: set text(size: 8pt, fill: rgb("475569"))
$body$
