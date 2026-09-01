# LOINC 2.83 Source Review

Review date: 2026-09-01

## Source identity

- Authority: Regenstrief Institute, Inc. and the LOINC Committee
- Acquisition: manual authenticated download from
  `https://loinc.org/download/loinc-complete/`
- Original filename: `Loinc_2.83.zip`
- Source version: `2.83`
- Release date: 2026-08-19
- Size: `92,815,327` bytes
- SHA-256: `077a0718e87d8309ffe3a673f75b836a8e783dc36a646413ef97c71c12eab27e`
- Archive integrity: all 95 entries pass CRC validation
- Archive bounds: 1,063,582,650 uncompressed bytes; largest member 246,622,108 bytes;
  maximum observed compression ratio 24.9195

The private source archive remains under `tmp/` and is not a release artifact or
Git-tracked file.

## Selected members

| Role | Member | Rows | Bytes | SHA-256 |
|---|---|---:|---:|---|
| Core | `LoincTable/Loinc.csv` | 112,405 | 84,205,426 | `5de1463f0fe65d6c97867153b43151a07ce3f8c8a86de681f98e110008032aba` |
| Chinese linguistic variant | `AccessoryFiles/LinguisticVariants/zhCN5LinguisticVariant.csv` | 96,518 | 96,195,744 | `94527f0d89c455c427ac75e2ae6f5f9b19a92534e2b206768375819734a186e5` |
| Part dictionary | `AccessoryFiles/PartFile/Part.csv` | 74,937 | 8,038,858 | `743dff07ad47bc5eeb4854864ebb2a5ed883112df8d49e21b0fad9bf60ad6c77` |
| Primary Part links | `AccessoryFiles/PartFile/LoincPartLink_Primary.csv` | 685,901 | 118,680,671 | `31e2db4ad083c56829951464d521956fb3bbd6ab9f207b5e9f39423363617578` |
| Panels and forms | `AccessoryFiles/PanelsAndForms/PanelsAndForms.csv` | 98,519 | 34,791,992 | `54451baebd4e6f116edfc44024fc5ea2a005e32a56ad72514c31278cff9ce7d4` |
| License | `LoincLicense_5.8.txt` | n/a | 25,709 | `05eb5069f8352b0513fe8c911d8a432e8ddc2d09f999b6f153617f2afd16ad85` |

The Chinese member is the official `zh`/`CN` variant with ID `5`. Its producer
is recorded in the source package as “Lin Zhang, A LOINC volunteer from China”.
All 96,518 rows contain translated Component, Property, Time, System, Scale,
Class, and Related Names; 47,983 also contain Method. The direct translated
Long Common Name, Short Name, Linguistic Variant Display Name, and Consumer Name
columns are empty in this release. `zh_display` is therefore a deterministic
fully-specified-name projection of the non-empty translated six axes. The exact
source fields remain unchanged in `translation_metadata_json`.

## Validation baselines

- Core status distribution: ACTIVE 99,737; TRIAL 5,436; DEPRECATED 5,008;
  DISCOURAGED 2,224
- ORDER_OBS: Order 5,466; Observation 34,517; Both 56,304; Subset 878; null 15,240
- Candidate UCUM links: 45,207 links across 44,521 LOINC codes
- Primary SYSTEM Part links: 112,405, one for every core code
- Panel/member links: 95,705 after excluding 2,814 structural self-link rows where
  `ParentLoinc == Loinc` (including 2,791 explicit `ParentId == ID` roots)
- Panel internal `(ParentId, ID)` pairs are unique for all selected links

`ucumvert` 0.3.2 validates 662 of the 664 distinct official UCUM expressions.
The two source-pinned expressions `k[arb'U]/L` and `m[arb'U]/mL` are recorded as
parser exceptions because the source uses valid prefixed arbitrary-unit syntax
that this parser version does not currently accept. No other parser failure is
allowed.

## Rights decision

The package contains `LoincLicense_5.8.txt`. The review records these operative
conditions without replacing the source license:

- the Licensed Materials may be used, copied, and distributed for commercial or
  non-commercial purposes subject to the license;
- Group 1 and Group 3 field contents may not be changed; new fields may be added;
- incorporated content must remain associated with its LOINC identifier and an
  allowed display name;
- the Section 10 attribution notice must accompany the product;
- applicable third-party copyright notices and terms must be retained or the
  affected third-party content must be removed;
- version information should be retained;
- the Part content may only be used in the licensed LOINC context.

This Candidate preserves the core and Chinese source values, LOINC identifiers,
English display, version and status. It retains core and panel external copyright
notices in canonical metadata and packages both the full source license and the
Section 10 short notice.

LOINC 2.83 contains 7,355 core rows and 15,795 source panel rows with external
copyright notices; 15,293 of those panel notices remain on selected member edges.
The compiler does not establish compliance with every
referenced third-party license. Therefore the reviewed state is
`redistribution: normalized-only` with `releaseEligible: false`: local builds are
allowed, but this Candidate must not enter a public signed Registry until an
artifact-specific third-party terms review is completed.
