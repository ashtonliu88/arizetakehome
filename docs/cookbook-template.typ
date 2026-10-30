#set document(title: "Trace Evidence Lab", author: "Ashton Liu")
#set page(paper: "us-letter", margin: (x: 0.75in, y: 0.7in),
  header: context { if counter(page).get().first() > 1 {
    text(size: 8pt, fill: rgb("64748b"))[TRACE EVIDENCE LAB / RESEARCH COOKBOOK]
  } },
  footer: context align(right, text(size: 8pt, fill: rgb("64748b"), counter(page).display("1"))))
#set text(font: "Libertinus Serif", size: 10pt, fill: rgb("14283f"))
#set par(justify: false, leading: 0.6em)
#set heading(numbering: none)
#show heading.where(level: 1): it => {
  block(above: 10pt, below: 6pt, sticky: true,
    text(font: "Libertinus Serif", size: 22pt, weight: "bold", fill: rgb("123e59"), it.body))
}
#show heading.where(level: 2): it => {
  block(above: 8pt, below: 5pt, sticky: true,
    text(font: "Libertinus Serif", size: 15pt, weight: "bold", fill: rgb("126d73"), it.body))
}
#show heading.where(level: 3): it => {
  block(above: 6pt, below: 4pt, sticky: true,
    text(font: "Libertinus Serif", size: 11pt, weight: "bold", it.body))
}
#show raw: set text(font: "DejaVu Sans Mono", size: 7.2pt)
#show raw.where(block: true): it => block(width: 100%, fill: rgb("f1f5f8"),
  inset: 8pt, radius: 3pt, breakable: true, it)
#show table: set text(size: 8pt)
#set table(inset: 5pt, stroke: 0.35pt + rgb("cbd5e1"), fill: (x, y) => if y == 0 { rgb("e5eff3") })
#set figure(gap: 5pt)
#show link: set text(fill: rgb("0c7287"))
$body$
