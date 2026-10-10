"""Remove model reasoning markup before streaming, storing or displaying answers."""
class AnswerFilter:
    tags = ('<think>', '</think>', '<analysis>', '</analysis>', '<reasoning>', '</reasoning>')

    def __init__(self):
        self.pending = ''
        self.hidden = False

    def feed(self, chunk):
        self.pending += chunk
        result = []
        while self.pending:
            lower = self.pending.lower()
            tag = next((t for t in self.tags if lower.startswith(t)), None)
            if tag:
                self.hidden = not tag.startswith('</')
                self.pending = self.pending[len(tag):]
                continue
            if any(t.startswith(lower) for t in self.tags):
                break
            if not self.hidden:
                result.append(self.pending[0])
            self.pending = self.pending[1:]
        return ''.join(result)

    def finish(self):
        result = '' if self.hidden or self.pending.startswith('<') else self.pending
        self.pending = ''
        return result

def visible_answer(text):
    # Legacy templates prefilled an opening tag outside the stored response.
    for tag in ('think','analysis','reasoning'):
        closing = '</'+tag+'>'
        if closing in text.lower() and '<'+tag+'>' not in text[:text.lower().index(closing)].lower():
            text = text[text.lower().index(closing)+len(closing):]
    if text.lower().startswith('хорошо, пользователь') and '/no_think' in text:
        return ''  # Legacy Thinking-only model exposed its untagged prefill.
    parser = AnswerFilter()
    return parser.feed(text) + parser.finish()
