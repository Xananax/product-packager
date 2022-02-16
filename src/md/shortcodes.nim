import std/
  [ logging
  , re
  , os
  , sequtils
  , strformat
  , strutils
  , sugar
  , tables
  ]
import parser
import utils


proc contentsShortcode(mdBlock: Block, mdBlocks: seq[Block], fileName: string): string =
  try:
    let
      levels = 2 .. (if mdBlock.args.len > 0: parseInt(mdBlock.args[0]) else: 3)
      headingToAnchor = proc(b: Block): string = b.heading.toLower.multiReplace({SPACE: "-", "'": "", "?": "", "!": ""})
      listBody = collect:
        for mdBlock in mdBlocks:
          if mdBlock.kind == bkHeading and mdBlock.level in levels:
            SPACE.repeat(2 * (mdBlock.level - 2)) & "- [" & mdBlock.heading & "](#" & mdBlock.headingToAnchor & ")"

    if listBody.len == 0:
      raise newException(ValueError, fmt"No valid headings found for ToC. Skipping...")

    result = @[Paragraph(@["Contents:"]), Blank(), List(listBody)].map(render).join(NL)

  except ValueError:
    result = mdBlock.render
    fmt"{fileName}:{result}: {getCurrentExceptionMsg()}".warn


proc linkShortcode(mdBlock: Block, mdBlocks: seq[Block], fileName: string): string =
  try:
    let
      argName = mdBlock.args[0]
      link = cache
        .findFile(argName & (if argName.endsWith(MD_EXT): "" else: MD_EXT))
        .replace(MD_EXT, HTML_EXT)
        .relativePath(fileName.parentDir, sep = '/')
    result = fmt"[{argName.splitFile.name}]({link})"

  except ValueError:
    result = mdBlock.render
    error fmt"{fileName}:{result}: {getCurrentExceptionMsg()}"


proc includeShortcode(mdBlock: Block, mdBlocks: seq[Block], fileName: string): string =
  try:
    if mdBlock.args.len > 2:
      raise newException(ValueError, fmt"Got {mdBlock.args.len} arguments, but expected 2 or less. Skipping...")

    let
      argName = mdBlock.args[0]
      includeFileName = cache.findFile(argName & (if argName.endsWith(GD_EXT) or argName.endsWith(SHADER_EXT): "" else: GD_EXT))

    result = readFile(includeFileName)

    if mdBlock.args.len == 2:
      let
        argAnchor = mdBlock.args[1]
        regexAnchor = fmt"\h*#\h*ANCHOR:\h*{argAnchor}\s*(.*?)\s*#\h*END:\h*{argAnchor}".re({reDotAll})

      var matches: array[1, string]
      if not result.contains(regexAnchor, matches):
        raise newException(ValueError, "Can't find matching contents for anchor. Skipping...")

      result = matches[0]

  except ValueError:
    result = mdBlock.render
    error fmt"{fileName}:{result}: {getCurrentExceptionMsg()}"


proc noOpShortcode*(mdBlock: Block, mdBlocks: seq[Block], fileName: string): string =
  result = mdBlock.render
  error fmt"{fileName}:{result}: Got malformed shortcode. Skipping..."


const SHORTCODES* =
  { "include": includeShortcode
  , "link": linkShortcode
  , "contents": contentsShortcode
  }.toTable

