// Step 1: Get distinct second_resource_ids
val secondResourceIds = catalog_relationship.select(col("second_resource_id")).distinct()

// Step 2: Perform LEFT ANTI JOIN to filter rows where first_resource_id has no matching second_resource_id (top-level parents)
val getTopLevelParent = catalog_relationship
  .select(
    col("first_resource_id").alias("destination"),
    lit(null).cast("string").alias("source"),
    col("first_resource_id").alias("root")
  )
  .join(secondResourceIds, col("destination") === col("second_resource_id"), "left_anti")  // Manual LEFT ANTI JOIN
  .drop("second_resource_id")

// Step 3: Recursively build the hierarchy
var secondResourceDF = catalog_relationship.as("al")
  .join(getTopLevelParent.as("gtlp"), col("gtlp.destination") === col("al.first_resource_id"))
  .select(
    col("al.second_resource_id").alias("destination"),
    col("al.first_resource_id").alias("source"),
    col("gtlp.root")
  )

// Track iterations and counts to avoid missing records
var iterationCount = 0
while (secondResourceDF.count() > 0 && iterationCount < 100) { // Prevent infinite loop
  println(s"Iteration: $iterationCount, Records in secondResourceDF: ${secondResourceDF.count()}")

  // Add the recursive result to TopLevelEs and continue joining
  val updatedDF = catalog_relationship.as("al")
    .join(secondResourceDF.as("gtlp"), col("gtlp.destination") === col("al.first_resource_id"))
    .select(
      col("al.second_resource_id").alias("destination"),
      col("al.first_resource_id").alias("source"),
      col("gtlp.root")
    )

  secondResourceDF = updatedDF

  iterationCount += 1
}

// Combine the final results
val TopLevelEs = getTopLevelParent.unionAll(secondResourceDF)
