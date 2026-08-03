import re


MAX_TAGLINE_LENGTH = 40


# These are deliberate copy edits for source taglines that cannot be shortened
# cleanly with the reusable phrase rules below. Keeping the original as the key
# makes every non-mechanical edit explicit and reviewable.
EXACT_REWRITES = {
    "A heart full of love and a head full of dreams.": "A heart full of love & dreams.",
    "Adventure, love, and spontaneous moments.": "Adventure, love & spontaneous moments.",
    "Adventurous heart, hopeless romantic soul.": "Adventurous heart, romantic soul.",
    "Adventurous spirit with a romantic heart.": "Adventurous spirit, romantic heart.",
    "Believer in fate, tacos, and good playlists.": "Fate, tacos & good playlists.",
    "Believer in good energy and great connections.": "Believer in good vibes & connection.",
    "Believer in love, fate, and second chances.": "Believer in love, fate & second chances.",
    "Believer in love, laughter, and second chances.": "Love, laughter & second chances.",
    "Believer in love, romance, and second chances.": "Love, romance & second chances.",
    "Believer in second chances and great love stories.": "Second chances & great love stories.",
    "Best friend material, upgradeable to soulmate.": "Best friend material, soulmate-ready.",
    "Book lover, adventure seeker, and pizza enthusiast.": "Books, adventure & pizza enthusiast.",
    "Brunch enthusiast with a side of sarcasm.": "Brunch enthusiast with a sarcastic side.",
    "Dancing through life, literally and figuratively.": "Dancing through life in every way.",
    "Dog lover, coffee drinker, and dream chaser.": "Dog lover, coffee drinker & dreamer.",
    "Dog parent, beach lover, wine enthusiast.": "Dog parent, beach lover & wine fan.",
    "Dog parent, coffee lover, and road trip junkie.": "Dog parent, coffee lover & road-tripper.",
    "Dreaming big, laughing often, loving deeply.": "Dreaming big, laughing & loving deeply.",
    "Dreaming of late-night talks and long walks.": "Late-night talks & long walks.",
    "Dreaming of love, adventure, and long walks.": "Dreaming of love, adventure & walks.",
    "Fluent in fun, romance, and silly dance moves.": "Fun, romance & silly dance moves.",
    "Fun-loving, slightly ridiculous, and full of heart.": "Fun-loving, silly & full of heart.",
    "Genuine connections over mindless swipes.": "Real connections over mindless swipes.",
    "Good vibes, great times, and even better company.": "Good vibes, great times & company.",
    "Great energy, great company, great times.": "Great energy, company & good times.",
    "Happiness is homemade—let’s cook together.": "Happiness is homemade—let’s cook.",
    "Here for real connections, not just small talk.": "Here for connection, not small talk.",
    "Here to make memories, not just small talk.": "Here to make memories, not small talk.",
    "Hopeless romantic with a touch of mischief.": "Mischievous hopeless romantic.",
    "If you bring coffee, I’ll bring the smiles.": "Bring coffee, I’ll bring the smiles.",
    "If you can’t handle my puns, we can’t date.": "Can’t handle my puns? We can’t date.",
    "In search of my partner in crime (and brunch).": "Seeking my partner in crime & brunch.",
    "I’ll bring the fun, you bring the snacks.": "I’ll bring fun; you bring the snacks.",
    "Just a goofball looking for my partner in crime.": "Goofball seeking a partner in crime.",
    "Laugh often, love deeply, and enjoy every moment.": "Laugh often, love deeply, enjoy it all.",
    "Laughing my way through life—want to join?": "Laughing through life—want to join?",
    "Let’s be the plot twist we never expected.": "Let’s be the plot twist we never saw.",
    "Let’s make this an adventure to remember.": "Let’s make it an adventure to remember.",
    "Let’s turn this swipe into something special.": "Let’s make this swipe something real.",
    "Life’s better with someone to share it with.": "Life’s better when it’s shared.",
    "Life’s too short for boring love stories.": "Life’s too short for boring romance.",
    "Living for great stories and greater people.": "Living for great stories & good people.",
    "Looking for love that lasts longer than a swipe.": "Seeking love beyond the swipe.",
    "Looking for love, fueled by coffee and optimism.": "Seeking love, coffee & optimism.",
    "Looking for love, laughter, and late-night drives.": "Love, laughs & late-night drives.",
    "Looking for love, laughter, and random adventures.": "Love, laughs & random adventures.",
    "Looking for someone to make bad decisions with.": "Seeking a partner for bad decisions.",
    "Looking for something real, not just really fun.": "Seeking something real and really fun.",
    "Looking for sparks that turn into something real.": "Seeking sparks that turn into real love.",
    "Lover of books, coffee, and meaningful moments.": "Books, coffee & moments that matter.",
    "Loving life and looking for someone to join.": "Loving life & seeking someone to join.",
    "Netflix, pizza, and deep convos? Yes, please.": "Netflix, pizza & deep talks? Yes.",
    "Passionate about love, life, and great food.": "Passionate about love, life & good food.",
    "Passionate about passion and late-night talks.": "Passionate about passion & late nights.",
    "Professional napper, aspiring world traveler.": "Pro napper, aspiring world traveler.",
    "Professional overthinker, part-time fun-haver.": "Pro overthinker, part-time fun-haver.",
    "Romance should be fun—let’s make it happen.": "Romance should be fun—let’s make it so.",
    "Romance, adventure, and a touch of mischief.": "Romance, adventure & some mischief.",
    "Romantic at heart, spontaneous by nature.": "Romantic heart, spontaneous nature.",
    "Searching for love and someone to split fries with.": "Seeking love & someone to share fries.",
    "Seeking a partner in crime (for fun things).": "Seeking a fun partner in crime.",
    "Seeking love, laughter, and endless playlists.": "Love, laughs & endless playlists.",
    "Seeking someone to make bad decisions with.": "Seeking a partner for bad decisions.",
    "Slightly introverted, highly interesting.": "Slightly introverted, very interesting.",
    "Spontaneous adventurer looking for a plus one.": "Spontaneous adventurer seeks a plus-one.",
    "Sunshine, road trips, and a little mischief.": "Sunshine, road trips & some mischief.",
    "Swipe right if you love deep convos and good vibes.": "Deep convos & good vibes? Swipe right.",
    "Swipe right if you love good coffee and deep talks.": "Good coffee & deep talks? Swipe right.",
    "Swipe right if you love last-minute road trips.": "Last-minute road trips? Swipe right.",
    "Swipe right, let’s make a story together.": "Swipe right—let’s write a story.",
    "The best love stories start with a laugh.": "The best love stories start with laughs.",
    "The best relationships start with a laugh.": "Great relationships start with laughs.",
    "Will bring laughter and snacks to every date.": "Bringing laughs & snacks to every date.",
    "Witty banter appreciated, deep convos required.": "Witty banter; deep talks required.",
    "Witty, charming, and a little unpredictable.": "Witty, charming & unpredictable.",
    "Writer of bad poetry, lover of good books.": "Bad poet, good-book lover.",
    "Your future adventure buddy is one swipe away.": "Your future adventure buddy is here.",
    "Your future partner in crime (for good things).": "Your future partner in good trouble.",
    "Your new favorite human, waiting to meet you.": "Your new favorite human is ready.",
    "Your new favorite person, waiting to be found.": "Your new favorite person is ready.",
    "Your next best decision might be this swipe.": "This swipe might be your best decision.",
    "Your next favorite distraction, guaranteed.": "Your next favorite distraction awaits.",
}


PHRASE_REWRITES = (
    ("Swipe right if you love ", "Love "),
    ("Swipe right if you enjoy ", "Enjoy "),
    ("Swipe right for ", "Here for "),
    (", staying for the ", " and "),
    ("meaningful conversations", "real talks"),
    ("great conversations", "great talks"),
    ("deep conversations", "deep talks"),
    ("late-night conversations", "late-night talks"),
    ("meaningful convos", "real talks"),
    ("deep convos", "deep talks"),
    ("conversations", "chats"),
    ("conversation", "chat"),
    ("unforgettable moments", "great memories"),
    ("endless laughter", "big laughs"),
    ("contagious laughter", "big laughs"),
    ("laughter", "laughs"),
    ("a little bit of", "a little"),
    ("spontaneous adventures", "adventures"),
    ("spontaneous adventure", "adventure"),
    ("spontaneous road trips", "road trips"),
    ("spontaneous getaways", "getaways"),
    ("spontaneous plans", "random plans"),
    ("spontaneous moments", "random moments"),
    ("spontaneous fun", "random fun"),
    ("second chances", "new chances"),
    ("always up for an adventure", "always up for adventure"),
    ("with a love for", "who loves"),
    ("a love for", "a love of"),
    ("even better", "better"),
    ("we’ll get along great", "we’ll click"),
    ("we’ll get along", "we’ll click"),
    ("we’re already a match", "we’ll click"),
    ("Looking for", "Seeking"),
    ("Searching for", "Seeking"),
    ("In search of", "Seeking"),
    ("meaningful", "real"),
    ("ridiculous", "silly"),
    ("adventurous", "bold"),
    ("professional", "pro"),
    ("unexpected adventure", "next adventure"),
    ("genuine connections", "real connections"),
    ("someone who makes life interesting", "someone fun"),
    ("one swipe away", "right here"),
    ("waiting to meet you", "ready to meet you"),
    ("waiting to be found", "ready to be found"),
    (", and ", " & "),
    (" and ", " & "),
    ("great ", ""),
)


def rewrite_tagline(tagline):
    """Return complete, natural copy within the product's 40-character limit."""
    tagline = tagline.strip()
    if len(tagline) <= MAX_TAGLINE_LENGTH:
        return tagline

    if tagline in EXACT_REWRITES:
        rewritten = EXACT_REWRITES[tagline]
    else:
        rewritten = tagline
        for original, replacement in PHRASE_REWRITES:
            if len(rewritten) <= MAX_TAGLINE_LENGTH:
                break
            rewritten = rewritten.replace(original, replacement)

        if tagline.startswith("Swipe right if you love ") and rewritten.startswith("Love "):
            rewritten = rewritten.removesuffix(".") + "? Swipe right."
        elif tagline.startswith("Swipe right if you enjoy ") and rewritten.startswith("Enjoy "):
            rewritten = rewritten.removesuffix(".") + "? Swipe right."

        if len(rewritten) > MAX_TAGLINE_LENGTH:
            rewritten = re.sub(
                r", one (?:date|smile|swipe|moment|misstep) at a time\.$",
                ".",
                rewritten,
            )
            rewritten = re.sub(r" one swipe at a time\.$", ".", rewritten)

    if len(rewritten) > MAX_TAGLINE_LENGTH:
        raise ValueError(
            f"No safe rewrite for {tagline!r}: result is {len(rewritten)} characters."
        )
    return rewritten
