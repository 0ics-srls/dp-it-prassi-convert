# dp-it-prassi-convert

Class of the it-prassi package (open-lex-it phase 80). See README sections as the class grows.

## Estremi (number of the act)

The number of the source metadata (grab sidecar, DocTrib file name) wins over the number read from the text (text layer or OCR). A disagreement keeps the source number and is recorded as a plan warning (`estremi: numero N letto dall'atto (testo|ocr) differisce dal numero della fonte M`). Only a number that came from a guess (file name, header) is corrected by the act.
