# EventPulse: Evaluation Phase - 1 Presentation Deck

**Institution:** Department of Information Science & Engineering, RV College of Engineering®  
**Course:** Development and Operations (DevOps) (`IS374TFA`)  
**Academic Year:** 2026–27  
**Motto:** *"Go, change the world"* ®  

**Project Title:**  
**EventPulse: An Event-Driven, High-Concurrency Distributed Ticketing & Flash-Sale Engine**  

**Carried Out By:**
- **Vinay Sinnur** (`1RV23IS138`)
- **Vinayak Kumar Singh** (`1RV23IS139`)
- **Swayam Prayash Pal** (`1RV23IS128`)

**Guide:**
- **Assistant Professor B K Srinivas**, Department of Information Science & Engineering, RVCE

---

## Slide 1: Title Slide (Page 1 / 6)
- **Course:** Development and Operations (DevOps) (`IS374TFA`)
- **Evaluation:** Phase - 1
- **Academic Year:** 2026–27
- **Project:** EventPulse: An Event-Driven, High-Concurrency Distributed Ticketing & Flash-Sale Engine
- **Department:** Department of Information Science & Engineering, RVCE

---

## Slide 2: Topic Relevance to the Course (5 Marks) (Page 2 / 6)
> *[Corrected slide number from 3 to 2]*

- **Immutable Containerization:** Multi-stage Docker builds package polyglot services consistently, eliminating environment drift between development and production.
- **Infrastructure as Code (IaC):** Terraform & LocalStack automate repeatable provisioning of queues (SQS), topics (SNS), and storage (S3).
- **Automated CI/CD & DevSecOps:** GitHub Actions pipelines run automated testing, linting, and Trivy container vulnerability scans before staging rollout.
- **Kubernetes Orchestration:** Kind/Minikube enables auto-scaling (HPA), self-healing health probes (liveness & readiness), and zero-downtime rolling updates.
- **Continuous Verification:** Automated k6/JMeter load tests validate flash-sale resilience (0 double bookings under concurrency) and track DORA metrics (Lead Time, MTTR, Deployment Frequency).

---

## Slide 3: Existing Approaches / Literature Review (5 Marks) (Page 3 / 6)

| Research Paper Title & Authors | Relevance to Our Project (EventPulse) |
| :--- | :--- |
| **"BASE: An Acid Alternative"**<br>by *Dan Pritchett (ACM Queue)* | Justifies dropping slow SQL Two-Phase Commits (2PC) in favor of eventual consistency, Message Queues, and the Transactional Outbox pattern used in our checkout flow. |
| **"Design and Implementation of High Concurrency Ticketing System Based on Redis and RabbitMQ"**<br>by *Y. Zhang, et al. (IEEE)* | Directly validates our choice of using Redis Lua scripts for atomic sub-millisecond seat holds and RabbitMQ for asynchronous ticket processing. |
| **"Microservices: Yesterday, Today, and Tomorrow"**<br>by *Nicola Dragoni, et al.* | Provides the theoretical foundation for our Bounded Contexts, mathematically justifying why isolating the read-heavy seatmap from the write-heavy reservation engine prevents system crashes. |
| **"Performance Evaluation of Microservices in Docker and Kubernetes"**<br>by *D. N. Jha, et al.* | Supports our container orchestration strategy, detailing how Kubernetes Horizontal Pod Auto-scaling and health probes handle sudden flash-sale traffic spikes. |
| **"Infrastructure as Code: A Systematic Literature Review"**<br>by *J. C. e Silva, et al.* | Backs our DevOps methodology of using Terraform and LocalStack to eliminate manual configuration drift and deploy fully reproducible cloud-native environments. |

---

## Slide 4: Application of the Topic (5 Marks) (Page 4 / 6)
> *[Corrected slide number from 3 to 4]*

- **Live Entertainment & Ticketing:** Platforms like BookMyShow and Ticketmaster handling concert and sports flash-sale surges without overselling seats or server timeouts.
- **E-Commerce Flash Sales:** Amazon Prime Day and Flipkart Big Billion Days managing strictly limited SKU inventory and cart holds with TTL expirations.
- **Travel & Transit Booking:** IRCTC Tatkal and airline reservation windows enforcing strict payment hold timeouts without database deadlock cascades.
- **University & Campus Portals:** High-concurrency college fest registrations (e.g., RVCE 8th Mile), hackathon sign-ups, and hostel room allotments where thousands hit simultaneously at 00:00.

---

## Slide 5: Tools Required (5 Marks) (Page 5 / 6)
> *[Corrected slide number from 3 to 5]*

| Category | Tool / Technology | Purpose in Demonstration |
| :--- | :--- | :--- |
| **Container & Orchestration** | Docker, Kubernetes (Kind/Minikube) | Multi-container isolation and automated rolling deployments. |
| **Cloud Emulation & IaC** | Terraform, LocalStack | Version-controlled, declarative AWS infrastructure setup (SQS, SNS, S3). |
| **CI/CD & Security** | GitHub Actions, Trivy | Automated build pipelines, testing, and container vulnerability scanning. |
| **Concurrency & Caching** | Redis | Atomic, sub-millisecond seat holding (Lua scripts) and rate limiting. |
| **Message Broker** | RabbitMQ / Apache Kafka | Asynchronous event queuing for CQRS and ticketing workflows. |
| **Polyglot Databases** | PostgreSQL, Apache Cassandra | Relational outbox storage (Postgres) and high-volume audit logging (Cassandra). |
| **Backend & Load Testing** | Python (FastAPI), Apache JMeter / k6 | Microservice APIs and simulating live flash-sale traffic spikes. |

---

## Slide 6: Thank You (Page 6 / 6)
> *[Corrected slide number from 3 to 6]*

- **EventPulse Live Demonstration:** Sub-millisecond atomic locking, CQRS segregation, and zero double-bookings under concurrent flash-sale load.
- **Interactive UI Portal:** [http://localhost:8000](http://localhost:8000)
- **OpenAPI 3.0 Specs:** [http://localhost:8000/docs](http://localhost:8000/docs)
