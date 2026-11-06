ReadableStreamDefaultController
const kmp = (pattern, text) => {
    const prefix = getPrefix(pattern);
    let i = 0;
    let j = 0;
    while (i < text.length) {
        if (pattern[j] === text[i]) {
            i++;
            j++;
        } else {
            j = prefix[j - 1];
        }
    }
}   