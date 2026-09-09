# MWONGOZO WA MTUMIAJI - MFUMO WA KIDIGITALI WA MEJAS MICROFINANCE (MMS)
## Comprehensive User Manual & Operational Documentation

---

### 1. UTANGULIZI WA MFUMO (System Introduction)

Mfumo wa **Mejas Microfinance Management System (MMS)** ni jukwaa la kisasa la kidigitali lililojengwa kwa ajili ya kurahisisha na kuboresha uendeshaji wa taasisi za kifedha na mikopo midogo midogo (Microfinance Institutions). Mfumo huu unaunganishwa na database thabiti ya wingu ya **Supabase PostgreSQL**, ikitoa usalama wa kiwango cha juu, upatikanaji wa haraka wa taarifa, na uwezo wa kuripoti kwa wakati halisi (real-time reports).

#### Sifa Kuu za Mfumo (Key Features):
1. **Usimamizi wa Matawi Mengi (Multi-Branch Management)**: Uwezo wa kusimamia matawi (Dar es Salaam, Arusha, Mwanza, Dodoma, n.k.) chini ya mfumo mmoja.
2. **Mgawanyo wa Majukumu (Role-Based Access Control - RBAC)**: Majukumu 5 tofauti (CEO/Mkurugenzi, Meneja wa Tawi, Mhasibu/Cashier, Afisa Mikopo, na Mteja).
3. **Ukadiriaji Mahiri wa Alama za Wateja (Client Credit Scoring)**: Mfumo unakadiria tabia ya mlipaji kiotomatiki:
   - **AAA (Excellent)**: Amemaliza mikopo yote bila kuchelewesha.
   - **AA (Good)**: Malipo thabiti na ucheleweshaji mdogo sana.
   - **C (Fair / At Risk)**: Ucheleweshaji wa mara kwa mara au mikopo iliyochelewa (Overdue).
   - **D (Default / High Risk)**: Mikopo iliyositishwa au madeni sugu (> 60 days).
4. **Injini ya Kiotomatiki ya Faini na Madeni Yaliyochelewa (Automated Overdue & Penalty Engine)**:
   - Hutambua kiotomatiki marejesho yaliyopitiliza tarehe ya malipo (`due_date < today`).
   - Huweka faini ya 5% ya kiasi kilichochelewa.
   - Hutuma taarifa za tahadhari (In-App Alerts) kwa Maafisa na Wasimamizi.
5. **Ufuatiliaji wa Marejesho ya Kila Siku (Daily Repayment Tracking)**:
   - Uchujaji kwa tarehe (Leo, Jana, Tarehe yoyote iliyopita au ijayo).
   - Viashiria vya Utendaji (KPIs): Jumla inayotarajiwa, Kiasi kilichokusanywa, Asilimia ya ukusanyaji (Collection Rate %), na Idadi ya mikopo iliyolipwa/ambayo haijalipwa.
   - Lebo za rangi: Kijani (Imelipwa), Njano (Nusu), Nyekundu (Haijalipwa).
   - Kitufe cha kutuma vikumbusho kwa wateja (Bulk SMS Reminders).
6. **Ripoti 7 Rasmi zenye Uhakiki wa PDF, Excel, na CSV**:
   - Upakuaji wa PDF rasmi wenye nembo na mihuri kwa kutumia injini ya **ReportLab**.
   - Upakuaji wa lahajedwali (Excel `.xlsx` na CSV).
7. **Kuingia kwa Bonyezo Moja (1-Click Test Login Pills)**:
   - Ukurasa wa kuingia una vitufe vya majaribio ya haraka kwa kila ngazi ya mtumiaji.

---

### 2. AKAUNTI ZA MAJARIBIO (Default Test Credentials)

Kwa ajili ya ukaguzi na matumizi ya haraka, mfumo una akaunti 5 maalum zilizosanidiwa:

| Jukumu (Role) | Jina la Mtumiaji (Username) | Nenosiri (Password) | Eneo la Ufikiaji (Access Scope) |
|---|---|---|---|
| **CEO / Director** | `ceo` | `CEO_password123` | Taasisi nzima, Matawi yote, Fedha zote, Ripoti za ngazi ya juu |
| **Branch Manager** | `manager` | `Manager_password123` | Tawi husika, Kuidhinisha mikopo, Kusimamia maafisa, Usuluhisho wa siku |
| **Cashier / Teller** | `cashier` | `Cashier_password123` | Kutoa mikopo, Kupokea marejesho, Kumbukumbu za fedha taslimu, EOD Balance |
| **Loan Officer** | `officer` | `Officer_password123` | Kusajili wateja, Kupokea maombi ya mikopo, Ufuatiliaji wa kila siku |
| **Client / Mteja** | `client` | `Client_password123` | Dashibodi ya mteja, Ratiba ya malipo, Kauli ya akaunti (Statement) |
| **Super Admin** | `admin` | `Admin_password123` | Usimamizi wa mfumo wa kiufundi na watumiaji wote |

> **Ushauri:** Kwenye ukurasa wa Kuingia (`/login/`), unaweza kubonyeza kitufe cha rangi cha jukumu lolote (k.m. *CEO*, *Manager*, *Cashier*, *Officer*, *Client*) na mfumo utajaza taarifa kiotomatiki na kukupeleka kwenye dashibodi husika.

---

### 3. MAJUKUMU NA MTIRIRIKO WA KAZI (Roles & Workflows)

#### 3.1 CEO / Mkurugenzi Mkuu (Executive Dashboard)
- **Kazi Kuu**:
  - Kuona taswira ya jumla ya taasisi (Total Loan Portfolio, Active Loans, Total Collected, Total Overdue, Net Cash Flow).
  - Grafu shirikishi za mapato na marejesho ya miezi 6.
  - Jedwali la ulinganifu wa utendaji kazi wa matawi mbalimbali (Branch Performance Matrix).
  - Kupakua ripoti zote za kiutendaji na kifedha kwa muundo wa PDF na Excel.

#### 3.2 Meneja wa Tawi (Branch Manager)
- **Kazi Kuu**:
  - Kupitia maombi ya mikopo yaliyoletwa na Maafisa wa Mikopo.
  - Kuidhinisha au kukataa mkopo kulingana na vigezo vya dhamana na Alama ya Mteja (Credit Score).
  - Kufanya uhakiki wa hesabu za kila siku (End-of-Day Reconciliation) zilizowasilishwa na Mhasibu.
  - Kufuatilia mikopo iliyochelewa (Overdue) katika tawi lake.

#### 3.3 Mhasibu / Cashier (Cash Desk Operations)
- **Kazi Kuu**:
  - **Kutoa Mikopo (Disbursement)**: Baada ya mkopo kuidhinishwa na meneja, mhasibu anatoa fedha na mfumo unarekodi mtiririko wa fedha (Cash Outflow).
  - **Kupokea Marejesho (Repayment Collection)**: Kurekodi malipo ya mkopaji (Cash, M-Pesa, TigoPesa, Airtel Money, Bank) na kutoa risiti.
  - **Ufungaji wa Siku (End-of-Day Reconciliation)**: Kurekodi kiasi cha kuanzia (Opening Cash), miamala ya siku, kiasi kilichopo (Physical Cash Count), na kuwasilisha kwa Meneja kwa uthibitisho.

#### 3.4 Afisa Mikopo (Loan Officer)
- **Kazi Kuu**:
  - **Usajili wa Wateja (Client Onboarding)**: Kuingiza taarifa za mteja (Jina, Simu, NIDA, Anwani, Biashara, na Tawi).
  - **Kuingiza Maombi ya Mkopo (Loan Application)**: Kuchagua aina ya mkopo, kiasi, muda (miezi), riba, na dhamana (Collateral).
  - **Ufuatiliaji wa Kila Siku (Daily Tracking)**: Kufungua ukurasa wa marejesho ya leo, kupiga simu kwa wanaodaiwa, na kutuma ujumbe wa ukumbusho (Bulk SMS Reminders).

#### 3.5 Mteja / Mkopaji (Client Portal)
- **Kazi Kuu**:
  - Kuingia kwenye akaunti yake na kuona muhtasari wa mkopo wake unaoendelea.
  - Kuona ratiba nzima ya marejesho na tarehe za malipo yajayo.
  - Kuona historia ya marejesho yote aliyofanya pamoja na risiti zake.
  - Kupakua taarifa ya mkopo (Loan Statement).

---

### 4. MWONGOZO WA HATUA KWA HATUA WA MATUMIZI (Step-by-Step Guide)

#### Hatua ya 1: Kusajili Tawi Jipya (Kama linahitajika)
1. Ingia kama **CEO** au **Meneja**.
2. Kwenye menyu ya pembeni, bonyeza **Matawi** (`/branches/`).
3. Bonyeza **Ongeza Tawi Jipya**.
4. Jaza Jina la Tawi, Msimbo (Branch Code), Mji/Mkoa, Simu, na Barua Pepe kisha bonyeza **Hifadhi**.

#### Hatua ya 2: Kusajili Mteja Mpya
1. Ingia kama **Afisa Mikopo** au **Meneja**.
2. Bonyeza **Wateja** -> **Sajili Mteja Mpya** (`/clients/new/`).
3. Jaza taarifa sahihi: NIDA (tarakimu 20), Nambari ya Simu, Jina kamili, na Tawi.
4. Mfumo utazalisha namba ya mteja (Client Number) kiotomatiki.

#### Hatua ya 3: Kuanzisha Maombi ya Mkopo
1. Fungua ukurasa wa mteja husika au nenda **Mikopo** -> **Ombi Jipya la Mkopo** (`/loans/apply/`).
2. Chagua Bidhaa ya Mkopo (k.m. Mkopo wa Biashara, Mkopo Binafsi, Mkopo wa Dharura).
3. Weka Kiasi Kinachoombwa, Muda (k.m. Miezi 3 au 6), na Asilimia ya Riba.
4. Ingiza taarifa za Dhamana (k.m. Gari, Kiwanja, Vyombo vya Biashara) na Wadhamini (Guarantors).
5. Wasilisha ombi. Hali itakuwa `SUBMITTED`.

#### Hatua ya 4: Kupitisha na Kuidhinisha Mkopo
1. Ingia kama **Meneja wa Tawi** au **CEO**.
2. Nenda kwenye orodha ya mikopo inayosubiri (`/loans/?status=SUBMITTED`).
3. Bonyeza maelezo ya mkopo, kagua Alama ya Mteja (Credit Score) na Dhamana.
4. Bonyeza **Idhinisha Mkopo (Approve)**. Hali itabadilika kuwa `APPROVED`.

#### Hatua ya 5: Kutoa Fedha (Disbursement)
1. Ingia kama **Mhasibu (Cashier)**.
2. Nenda **Mikopo** au kwenye Dashibodi ya Cashier penye *Mikopo Inayosubiri Kutolewa Fedha*.
3. Bonyeza **Toa Fedha (Disburse)**, chagua njia ya malipo (Cash au Bank Transfer) na rejea ya malipo.
4. Mfumo utatengeneza kiotomatiki:
   - Ratiba ya Marejesho (Repayment Schedule).
   - Rekodi ya Mtiririko wa Fedha (Cash Flow Outflow).
   - Hali ya mkopo inakuwa `ACTIVE`.

#### Hatua ya 6: Kurekodi Marejesho ya Kila Siku
1. Mteja anapofanya malipo, nenda **Marejesho** -> **Rekodi Malipo** (`/repayments/record/`).
2. Tafuta mkopo wa mteja, weka kiasi kilicholipwa, tarehe, na njia ya malipo (M-Pesa, Cash, Benki).
3. Hifadhi. Mfumo utapunguza salio la mkopo, kusasisha ratiba ya malipo, na kutoa risiti.
4. Ikiwa deni limeisha kabisa, mfumo utabadilisha hali ya mkopo kuwa `COMPLETED`.

#### Hatua ya 7: Ufuatiliaji wa Madeni na Faini za Kuchelewa
1. Kila siku unapoingia kwenye mfumo au unapofungua ukurasa wa **Ufuatiliaji wa Siku** (`/tracking/daily/`), mfumo hufanya uchunguzi wa kiotomatiki:
   - Ratiba zote ambazo tarehe ya malipo imepita na hazijalipwa zinawekwa alama nyekundu (`OVERDUE`).
   - Faini ya 5% huhesabiwa kiotomatiki.
   - Ikiwa deni limevuka siku 60, linawekwa daraja la `DEFAULTED`.
2. Bonyeza kitufe cha **Tuma Vikumbusho (Bulk SMS)** kuwatumia wateja wote wanaodaiwa ujumbe wa ukumbusho wa malipo mara moja.

#### Hatua ya 8: Kuzalisha Ripoti za PDF na Excel
1. Nenda **Ripoti** (`/reports/generate/`).
2. Chagua aina ya ripoti:
   - *Ripoti ya Mikopo Yote*
   - *Ripoti ya Marejesho*
   - *Ripoti ya Mikopo Iliyochelewa (Overdue/PAR)*
   - *Ripoti ya Utendaji wa Maafisa*
   - *Ripoti ya Mtiririko wa Fedha (Cash Flow)*
   - *Ripoti ya Wateja na Alama Zao*
   - *Ripoti ya Usuluhisho wa Siku (Reconciliation)*
3. Chagua tarehe ya kuanzia na ya mwisho, na tawi.
4. Chagua muundo unaotaka:
   - **Pakua PDF (Official)**: Kwa ajili ya uchapishaji wenye muundo rasmi wa mezani.
   - **Pakua Excel (.xlsx)**: Kwa ajili ya uchambuzi wa kina.
   - **Pakua CSV**: Kwa ajili ya kuunganisha na mifumo mingine.

---

### 5. USALAMA NA UTENDAJI KAZI (Security & Performance)

1. **Supabase Cloud Database**: Mfumo unahifadhi taarifa kwenye PostgreSQL iliyo na cheti cha SSL (Encrypted connection) na nakala salama za kiotomatiki (Automated Backups).
2. **Ulinzi wa Upatikanaji (CSRF & XSS Protection)**: Fomu zote na miamala inalindwa kwa viwango vya juu vya usalama vya Django.
3. **Kumbukumbu ya Matukio (Audit Logging)**: Kila tendo muhimu (kuingia, kutoa fedha, kuidhinisha mkopo, kufuta taarifa) linarekodiwa pamoja na mtumiaji aliyelifanya, tarehe, na wakati kamili.

---

### 6. MSAADA WA KIUFUNDI (Technical Support)

Ikiwa unahitaji msaada wowote wa kiufundi au marekebisho ya usanidi:
- **Barua Pepe**: `support@mejas-microfinance.co.tz`
- **Simu**: `+255 700 000 000`
- **Hifadhi ya Kanuni (Repository)**: `/home/sheddy/mejas-microfinance-system`
