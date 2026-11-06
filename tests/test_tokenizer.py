"""Tests for archon.formula.tokenizer."""

import unittest

from archon.formula.tokenizer import Token, TokenizeError, TokenType, tokenize


def types(tokens: list[Token]) -> list[TokenType]:
    """Helper: pull just the TokenType sequence out of a token list, dropping EOF."""
    return [t.type for t in tokens if t.type != TokenType.EOF]


def texts(tokens: list[Token]) -> list[str]:
    """Helper: pull just the text sequence out of a token list, dropping EOF."""
    return [t.text for t in tokens if t.type != TokenType.EOF]


class TestTokenize(unittest.TestCase):
    def test_strips_leading_equals(self):
        with_eq = tokenize("=1+1")
        without_eq = tokenize("1+1")
        self.assertEqual(texts(with_eq), texts(without_eq))

    def test_simple_arithmetic(self):
        tokens = tokenize("=1+2*3")
        self.assertEqual(
            types(tokens),
            [TokenType.NUMBER, TokenType.OP, TokenType.NUMBER, TokenType.OP, TokenType.NUMBER],
        )
        self.assertEqual(texts(tokens), ["1", "+", "2", "*", "3"])

    def test_decimal_and_exponent_numbers(self):
        tokens = tokenize("=1.5+2e3+.25")
        self.assertEqual(
            [t.text for t in tokens if t.type == TokenType.NUMBER],
            ["1.5", "2e3", ".25"],
        )

    def test_function_call_with_range(self):
        tokens = tokenize("=SUM(A1:A10)")
        self.assertEqual(
            types(tokens),
            [
                TokenType.IDENTIFIER,
                TokenType.LPAREN,
                TokenType.REF,
                TokenType.COLON,
                TokenType.REF,
                TokenType.RPAREN,
            ],
        )
        self.assertEqual(texts(tokens), ["SUM", "(", "A1", ":", "A10", ")"])

    def test_absolute_references_keep_dollar_signs(self):
        tokens = tokenize("=$A$1:$C$3")
        refs = [t.text for t in tokens if t.type == TokenType.REF]
        self.assertEqual(refs, ["$A$1", "$C$3"])

    def test_string_literal(self):
        tokens = tokenize('=A1&"hello"')
        strings = [t.text for t in tokens if t.type == TokenType.STRING]
        self.assertEqual(strings, ['"hello"'])

    def test_string_with_escaped_quote(self):
        tokens = tokenize('="say ""hi"""')
        strings = [t.text for t in tokens if t.type == TokenType.STRING]
        self.assertEqual(strings, ['"say ""hi"""'])

    def test_unterminated_string_raises(self):
        with self.assertRaises(TokenizeError):
            tokenize('="unterminated')

    def test_boolean_literals(self):
        tokens = tokenize("=TRUE+FALSE")
        self.assertEqual(
            [t.type for t in tokens if t.type == TokenType.BOOLEAN],
            [TokenType.BOOLEAN, TokenType.BOOLEAN],
        )
        self.assertEqual(
            [t.text for t in tokens if t.type == TokenType.BOOLEAN], ["TRUE", "FALSE"]
        )

    def test_comparison_operators_including_two_char(self):
        tokens = tokenize("=A1<=B1")
        self.assertIn("<=", texts(tokens))
        tokens2 = tokenize("=A1<>B1")
        self.assertIn("<>", texts(tokens2))
        tokens3 = tokenize("=A1>=B1")
        self.assertIn(">=", texts(tokens3))

    def test_cross_sheet_reference(self):
        tokens = tokenize("=Sheet1!A1")
        self.assertEqual(
            types(tokens), [TokenType.IDENTIFIER, TokenType.BANG, TokenType.REF]
        )

    def test_quoted_sheet_name_with_space(self):
        tokens = tokenize("='My Sheet'!B2")
        self.assertEqual(
            types(tokens), [TokenType.SHEET_NAME, TokenType.BANG, TokenType.REF]
        )
        self.assertEqual(texts(tokens)[0], "'My Sheet'")

    def test_quoted_sheet_name_with_escaped_quote(self):
        tokens = tokenize("='O''Brien''s Sheet'!A1")
        sheet_tok = tokens[0]
        self.assertEqual(sheet_tok.type, TokenType.SHEET_NAME)
        self.assertEqual(sheet_tok.text, "'O''Brien''s Sheet'")

    def test_postfix_percent(self):
        tokens = tokenize("=A1%")
        self.assertEqual(types(tokens), [TokenType.REF, TokenType.PERCENT])

    def test_whole_column_and_row_refs(self):
        tokens = tokenize("=SUM(A:A)")
        refs = [t.text for t in tokens if t.type == TokenType.REF]
        self.assertEqual(refs, ["A", "A"])

    def test_array_literal_braces_and_separators(self):
        tokens = tokenize("={1,2;3,4}")
        self.assertEqual(
            types(tokens),
            [
                TokenType.LBRACE,
                TokenType.NUMBER,
                TokenType.COMMA,
                TokenType.NUMBER,
                TokenType.SEMICOLON,
                TokenType.NUMBER,
                TokenType.COMMA,
                TokenType.NUMBER,
                TokenType.RBRACE,
            ],
        )

    def test_whitespace_is_ignored(self):
        tokens = tokenize("= 1 + 2 ")
        self.assertEqual(texts(tokens), ["1", "+", "2"])

    def test_function_name_not_mistaken_for_ref(self):
        tokens = tokenize("=SUM(A1)")
        self.assertEqual(tokens[0].type, TokenType.IDENTIFIER)
        self.assertEqual(tokens[0].text, "SUM")

    def test_every_token_has_correct_position(self):
        tokens = tokenize("=A1+B2")
        # positions are relative to the ORIGINAL formula, '=' included
        non_eof = [t for t in tokens if t.type != TokenType.EOF]
        self.assertEqual([t.pos for t in non_eof], [1, 3, 4])

    def test_error_position_is_relative_to_original_formula(self):
        try:
            tokenize("=A1@B2")
        except TokenizeError as exc:
            self.assertIn("position 3", str(exc))
        else:
            self.fail("expected TokenizeError")

    def test_unprefixed_whole_row_range(self):
        tokens = tokenize("=SUM(1:3)")
        refs = [t.text for t in tokens if t.type == TokenType.REF]
        self.assertEqual(refs, ["1", "3"])

    def test_unicode_digit_raises_tokenize_error_not_assertion(self):
        with self.assertRaises(TokenizeError):
            tokenize("=1+\u00b2")  # superscript two, not an ASCII digit

    def test_function_name_shaped_like_ref_is_identifier(self):
        tokens = tokenize("=LOG10(A1)")
        self.assertEqual(tokens[0].type, TokenType.IDENTIFIER)
        self.assertEqual(tokens[0].text, "LOG10")

    def test_function_after_colon_is_identifier_not_ref(self):
        tokens = tokenize("=SUM(A1:IF(B1,C1,D1))")
        ident_texts = [t.text for t in tokens if t.type == TokenType.IDENTIFIER]
        self.assertIn("IF", ident_texts)
        ref_texts = [t.text for t in tokens if t.type == TokenType.REF]
        self.assertNotIn("IF", ref_texts)

    def test_eof_token_present_at_end(self):
        tokens = tokenize("=1")
        self.assertEqual(tokens[-1].type, TokenType.EOF)

    def test_unrecognized_character_raises(self):
        with self.assertRaises(TokenizeError):
            tokenize("=A1@B2")


if __name__ == "__main__":
    unittest.main()
