

if __name__ == "__main__":
    prompt = """
    fetch the content of these three web pages and summarize each one of them in 100 words or less.

[Hacker News] A warning about 'model welfare'
<a href="https://news.ycombinator.com/item?id=49727580">Comments</a>
https://mustafa-suleyman.ai/a-warning-about-model-welfare
Top comments:
- First, OpenAI runs around screaming and yelling for OSS (and Chinese) models to be regulated and banned. Then Anthropic yells and screams the sky(net) is falling and going to kill us all, let's regulate and ensure AI has built in kill switches. And... Now Microsoft's turn. The rivalry is honestly becoming a joke. Can these big-tech corps grow the f*k up and play nicely in the sandpit?
- Summarized. > "AIs are not conscious. They do not feel, experience, or suffer. They do not have innate preferences or underlying motivations. They are sequence completion engines, internally hollow, designed to follow instructions, and accomplish goals set by humans." > He heavily criticised Anthropic for teaching its AI to have human-like qualities, a practice known as anthropomorphising, which m

[Hacker News] The DeepMind Institute
<a href="https://news.ycombinator.com/item?id=49727659">Comments</a>
https://institute.deepmind.com/
Top comments:
- Tl;DR: It's not a new organization, or non-profit institute. It's a Substack/blog. > DMI is a platform for researchers and thinkers from across Google DeepMind, Google, and the wider global research community to work on and publish creative, deeply informed ideas about a world with AGI. They will not always agree, and they will likely change their minds, as more data and information comes to light
- They are simply looking to steer AI policy discussions. It's basically an in-house think tank. It has all the trappings, especially with ominous prognostications like: Today’s AI systems have impressive capabilities and the rapid pace of innovation suggests we’re now approaching artificial general intelligence (AGI), a system that exhibits all the cognitive capabilities of the human brain. Not sur

[Hacker News] Claude Cowork and chat are now one Claude
<a href="https://news.ycombinator.com/item?id=49729412">Comments</a>
https://claude.com/blog/cowork-is-now-claude
Top comments:
- To Anthropic: I hope you don't merge Claude Code and chat, I like keeping their memory separate.
- I'm starting to explore alternative options because Claude has become an awful value proposition. Any suggestions?


"""

    client = Anthropic()  # reads ANTHROPIC_API_KEY from env automatically
    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )


    text = "".join(block.text for block in response.content if block.type == "text")
    # Strip stray markdown fences in case the model adds them despite instructions.
    text = re.sub(r"^```(?:html)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text.strip())
    # return text.strip()

    print(text)


