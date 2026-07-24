#!/usr/bin/env node
"use strict";

const readline = require("readline");
const { SOQLParser } = require("@salesforce/soql-common/soql-parser.lib");

const DEFAULT_CONFIG = {
  isApex: false,
  isMultiCurrencyEnabled: false,
  apiVersion: 60,
};

function parserConfig(overrides) {
  return {
    ...DEFAULT_CONFIG,
    ...(overrides || {}),
  };
}

function tokenToJson(token) {
  if (!token) {
    return null;
  }
  return {
    text: token.text,
    type: token.type,
    line: token.line,
    column: token.charPositionInLine,
  };
}

function errorToJson(error) {
  const token = typeof error.getToken === "function" ? error.getToken() : undefined;
  return {
    message: error.getMessage(),
    line: error.getLineNumber(),
    column: error.getCharacterPositionInLine(),
    token: tokenToJson(token),
  };
}

function tokensToJson(tokenStream) {
  if (!tokenStream || typeof tokenStream.getTokens !== "function") {
    return [];
  }
  return tokenStream
    .getTokens()
    .filter((token) => token.channel === 0)
    .map(tokenToJson);
}

function parseQuery(request) {
  const query = typeof request.query === "string" ? request.query : "";
  const parser = SOQLParser(parserConfig(request.config));
  const result = parser.parseQuery(query);
  const parseTree = result.getParseTree();
  return {
    id: request.id ?? null,
    success: result.getSuccess(),
    errors: result.getParserErrors().map(errorToJson),
    tokens: tokensToJson(result.getTokenStream()),
    parseTree: parseTree
      ? {
          type: parseTree.constructor ? parseTree.constructor.name : "",
          text: parseTree.text || "",
        }
      : null,
  };
}

function writeResponse(response) {
  process.stdout.write(`${JSON.stringify(response)}\n`);
}

const rl = readline.createInterface({
  input: process.stdin,
  crlfDelay: Infinity,
});

rl.on("line", (line) => {
  if (!line.trim()) {
    return;
  }
  try {
    const request = JSON.parse(line);
    writeResponse(parseQuery(request));
  } catch (error) {
    writeResponse({
      success: false,
      errors: [
        {
          message: error && error.message ? error.message : String(error),
          line: null,
          column: null,
          token: null,
        },
      ],
      tokens: [],
      parseTree: null,
    });
  }
});
