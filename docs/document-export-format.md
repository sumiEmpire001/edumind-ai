# Document Studio export format

Word and PDF downloads use A4 pages, one-inch margins, black headings, 12-point serif body text with 1.5 line spacing, and page-number footers. Word uses Times New Roman (with the reader's installed font substitution); PDF embeds DejaVu Serif when available. Both include a title page and section contents. PDF contents include calculated page numbers; Word's contents are an editable section list.

The exporters share a conservative Markdown parser: headings, bold, italics, inline code, fenced code, indented lists, and pipe tables. Word tables remain editable. Header rows repeat across pages. Source URLs are preserved in readable text. Source paragraphs are separated by blank lines; ordinary soft line breaks are joined.

Tables with more than six columns fall back to readable row text rather than discarding data. Complex LaTeX equations remain source notation; images are not embedded. These exports do not invent references, validate academic claims, or claim conformity to a particular university's thesis template. Word and PDF may paginate differently because their font metrics and layout engines differ.

Exports retain the existing 300,000-character content limit and PDF's 100-page limit. They never execute source HTML or fetch remote URLs. Tests cover document structure, Unicode, source preservation, long reports, repeating table headers, and access isolation. Render representative exports through LibreOffice and Poppler after layout changes.
