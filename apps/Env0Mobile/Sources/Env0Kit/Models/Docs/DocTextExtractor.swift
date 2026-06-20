import Foundation

/// Flattens a Google-Docs body structure into plain text.
///
/// The document's text is spread across
/// `body.content[].paragraph.elements[].textRun.content`, with each paragraph's
/// final `textRun` already ending in `"\n"`. This walks the structural-element
/// tree (descending into tables and tables-of-contents) and concatenates every
/// `textRun.content` in document order, reproducing what the spec describes as
/// "concatenate every `textRun.content`".
public enum DocTextExtractor {
    /// Concatenate the plain text of an ordered list of structural elements.
    public static func text(from elements: [StructuralElement]?) -> String {
        guard let elements else { return "" }
        var result = ""
        for element in elements {
            append(element, into: &result)
        }
        return result
    }

    private static func append(_ element: StructuralElement, into result: inout String) {
        if let paragraph = element.paragraph {
            for inline in paragraph.elements ?? [] {
                if let content = inline.textRun?.content {
                    result += content
                }
            }
        }
        if let table = element.table {
            for row in table.tableRows ?? [] {
                for cell in row.tableCells ?? [] {
                    for nested in cell.content ?? [] {
                        append(nested, into: &result)
                    }
                }
            }
        }
        if let toc = element.tableOfContents {
            for nested in toc.content ?? [] {
                append(nested, into: &result)
            }
        }
    }
}
