# Security Policy

## Reporting a Vulnerability

The following keys may be used to communicate sensitive information to developers:

| Name | Email | Fingerprint |
|------|-------|----------------|
| Doriancoin Project | admin@doriancoin.org | A4FA 47B9 A4CC F63A 2D6A 52F3 15EF 2B98 0170 6EB4 |
| ThomasV | thomasv@electrum.org | 6694 D8DE 7BE8 EE56 31BE D950 2BD5 824B 7F94 70E6 |
| SomberNight | somber.night@protonmail.com | 4AD6 4339 DFA0 5E20 B3F6 AD51 E7B7 48CD AF5E 5ED9 |

The Doriancoin Project key is the one that signs the `SHA256SUMS.asc` attached
to each Electrum-DSV release. The other two are the upstream Electrum
maintainers, for vulnerabilities in code inherited from upstream.

You can import a key by running the following command with that
individual’s fingerprint: `gpg --recv-keys "<fingerprint>"`
Ensure that you put quotes around fingerprints containing spaces.

These public keys can also be found in this git repository, in the top-level
`pubkeys` folder. The Doriancoin key is `pubkeys/doriancoin.asc`, which can be
imported directly without a keyserver:

    gpg --import pubkeys/doriancoin.asc
