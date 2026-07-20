def letter_to_num(char: str) -> str:
    """
    Takes letter and returns position in alphabet. Single digits prefixed with "0".

    "a" -> "01"
    """
    number = str(ord(char.lower()) - 96)
    if len(number) == 1:
        return "0" + number
    else:
        return number
