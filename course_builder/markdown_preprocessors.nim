import strutils
import strformat
import algorithm
import re
import gdscript_built_in_classes
import os


type
    Error* = ref object
        characterPosition: int
        message: string
        lineNumber: int

    ProcessedMarkdown* = ref object
        text: string
        errors: seq[Error]

proc replaceIncludeShortcode(filename: string, anchor: string): string =
    # TODO: Find file by filename, parse file and find content of anchor
    return ""

proc replaceLink(target: string, anchor: string = ""): string =
    # TODO: check if target is name of file, if yes, ensure it's in cache
    return ""

proc generateTableOfContents(): string =
    # TODO: check if target is name of file, if yes, ensure it's in cache
    return ""

proc replaceIconsInPlace(document: ProcessedMarkdown): ProcessedMarkdown =

    proc appendImageToIcon(match: string): string =
        #TODO: ensure it just trims the backticks
        let className = match[1 .. -2]
        # TODO: find image file path from class name
        let
            path = ""
            basename = lastPathPart(path)
        result = """<img src="{path}" alt="{basename}" />""".fmt & " " & match

    const RegexGDScriptClass = re("`" & join(GDScriptBuiltInClasses, "`|`") & "`")

    var searchStartIndex = 0
    var outputText = ""
    while true:
        let (start, last) = re.findBounds(document.text, RegexGDScriptClass, searchStartIndex)
        if start < 0: break
        outputText.add(document.text[searchStartIndex..<start])
        # process the match in start, last
        let match = document.text[start..last]
        searchStartIndex = last + 1
    #TODO: check that this does preserve errors in the `document`
    outputText.add(document.text[searchStartIndex..len(document.text)])
    result.text = outputText
    return result

# Finds patterns with the form {...} and passes them to the appropriate function
# to replace the shortcode.
# Returns the string with the shortcodes replaced.
# TODO: keep track of line count for error reporting?
proc replaceShortcodesInPlace(document: ProcessedMarkdown): ProcessedMarkdown =
    let content = document.text
    var
        previousStartIndex = 0
        shortcodeStartIndex = find(content, "{")
    if shortcodeStartIndex == -1:
        return ProcessedMarkdown(text: content, errors: @[])

    while shortcodeStartIndex != -1:
        result.text &= content[previousStartIndex..<shortcodeStartIndex]

        let endIndex = find(content, "}", shortcodeStartIndex)
        if endIndex == -1:
            result.errors.add(Error(characterPosition: shortcodeStartIndex,
                    message: "Unterminated shortcode"))

        # Parse and process supported shortcodes
        let shortcode = content[shortcodeStartIndex .. endIndex]
        var output = ""
        let arguments = shortcode[1 .. -1].split(" ")
        let shortcodeName = arguments[0]
        case shortcodeName:
            of "include":
                if arguments.len() != 3:
                    result.errors.add(Error(
                            characterPosition: shortcodeStartIndex,
                            message: "Include shortcode requires two arguments: the path or name of the file to include from and the anchor's name."))
                    break
                let
                    filename = arguments[1]
                    anchor = arguments[2]
                output = replaceIncludeShortcode(filename, anchor)
            of "link":
                let argumentCount = arguments.len()
                if argumentCount < 2:
                    result.errors.add(Error(
                            characterPosition: shortcodeStartIndex,
                            message: "Link shortcode requires at least one argument: the target file name or url."))
                    break
                output = replaceLink(arguments[1])
            of "table_of_contents":
                if arguments.len() != 1:
                    result.errors.add(Error(
                            characterPosition: shortcodeStartIndex,
                            message: "Table of contents shortcode requires no arguments."))
                    break
                output = generateTableOfContents()
            else:
                result.errors.add(Error(
                        characterPosition: shortcodeStartIndex,
                        message: "Unknown shortcode: " & shortcodeName))

        result.text &= output
        previousStartIndex = shortcodeStartIndex
        shortcodeStartIndex = find(content, "{", endIndex + 1)

proc runMarkdownPreprocessors*(content: string): ProcessedMarkdown =
    ProcessedMarkdown(text: content, errors: @[]).replaceShortcodesInPlace().replaceIconsInPlace()

# Calculates the line number for each error in the document. Modifies the line
# numbers in-place.
# To call on each document after collecting all errors during builds.
proc setErrorLineNumbers*(document: ProcessedMarkdown) =
    var
        lineNumber = 1
        lineStartIndex = 0
        lineEndIndex = find(document.text, "\n", lineStartIndex)

    let sortedErrors = sorted(document.errors, proc (a: Error, b: Error): int =
        cmp(a.characterPosition, b.characterPosition))

    for error in sortedErrors:
        while error.characterPosition >= lineEndIndex:
            lineStartIndex = lineEndIndex + 1
            lineEndIndex = find(document.text, "\n", lineStartIndex)
            lineNumber += 1
        error.lineNumber = lineNumber
